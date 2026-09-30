"""Ownership-based cleanup; preserve modified files and untracked knowledge."""
import hashlib
import json
import os
from pathlib import Path

from .distribution import MANAGED_ROOTS


def identity(path: Path):
    if path.is_symlink():
        return ["symlink", os.readlink(path)]
    if path.is_file():
        return ["file", hashlib.sha256(path.read_bytes()).hexdigest()]
    return None


def walk(root: Path):
    for name in MANAGED_ROOTS:
        start = root / name
        if not start.exists() and not start.is_symlink():
            continue
        if start.is_file() or start.is_symlink():
            yield name, start
            continue
        for directory, subdirs, files in os.walk(start, followlinks=False):
            base = Path(directory)
            subdirs[:] = [d for d in subdirs if d not in (".git", "__pycache__")]
            for child in subdirs + files:
                if child in (".git", ".gitignore") or child.endswith(".pyc"):
                    continue
                item = base / child
                if item.is_file() or item.is_symlink():
                    yield str(item.relative_to(root)), item


def manifest_path(root: Path) -> Path:
    return root / ".thesystem" / "managed.json"


def snapshot(source: Path, target: Path) -> int:
    managed = {}
    for relative, item in walk(source):
        mark = identity(item)
        if mark is not None and mark == identity(target / relative):
            managed[relative] = mark
    path = manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "entries": managed}, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, path)
    return len(managed)


def clean(target: Path) -> dict:
    path = manifest_path(target)
    if not path.is_file():
        raise SystemExit("refusing removal without ownership manifest")
    data = json.loads(path.read_text())
    if data.get("version") != 1 or not isinstance(data.get("entries"), dict):
        raise SystemExit("invalid ownership manifest")
    removed = 0
    retained = []
    for relative, expected in data["entries"].items():
        parts = Path(relative).parts
        if not parts or parts[0] not in MANAGED_ROOTS or ".." in parts or Path(relative).is_absolute():
            raise SystemExit("unsafe ownership manifest path")
        item = target / relative
        if not item.parent.resolve().is_relative_to(target.resolve()):
            raise SystemExit("unsafe symlink parent")
        if identity(item) == expected:
            item.unlink()
            removed += 1
        elif item.exists() or item.is_symlink():
            retained.append(relative)
    # Empty directories are safe to remove; non-empty/untracked ones survive.
    for name in MANAGED_ROOTS:
        item = target / name
        if item.is_dir() and not item.is_symlink():
            directories = sorted(
                (p for p in item.rglob("*") if p.is_dir() and not p.is_symlink()),
                key=lambda p: len(p.parts), reverse=True,
            )
            for directory in [*directories, item]:
                try:
                    directory.rmdir()
                except OSError:
                    pass
    return {"removed": removed, "retained_modified": retained}
