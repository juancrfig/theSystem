"""Ownership-based cleanup; preserve modified files and untracked knowledge."""
import hashlib
import json
import os
from pathlib import Path
import re

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


def read_manifest(root: Path, source: Path | None = None) -> dict:
    """Read and completely validate ownership metadata before callers mutate files."""
    root = Path(root)
    marker = root / ".thesystem"
    path = source or manifest_path(root)
    if marker.is_symlink() or (marker.exists() and not marker.is_dir()):
        raise SystemExit("unsafe ownership state directory")
    if path.is_symlink() or not path.is_file():
        raise SystemExit("refusing removal without ownership manifest")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit("invalid ownership manifest") from error
    if (not isinstance(data, dict) or set(data) != {"version", "entries"}
            or type(data["version"]) is not int or data["version"] != 1
            or not isinstance(data["entries"], dict)):
        raise SystemExit("invalid ownership manifest")
    for relative, expected in data["entries"].items():
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise SystemExit("unsafe ownership manifest path")
        item_path = Path(relative)
        parts = item_path.parts
        if not parts or parts[0] not in MANAGED_ROOTS or ".." in parts or item_path.is_absolute() or "." in parts:
            raise SystemExit("unsafe ownership manifest path")
        if (not isinstance(expected, list) or len(expected) != 2
                or expected[0] not in ("file", "symlink")
                or not isinstance(expected[1], str)
                or (expected[0] == "file" and not re.fullmatch(r"[0-9a-f]{64}", expected[1]))):
            raise SystemExit("invalid ownership manifest entry")
        item = root / item_path
        try:
            if not item.parent.resolve().is_relative_to(root.resolve()):
                raise SystemExit("unsafe symlink parent")
        except OSError as error:
            raise SystemExit("unsafe symlink parent") from error
    return data


def record_manifest(target: Path, entries: dict) -> int:
    path = manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "entries": entries}, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, path)
    return len(entries)


def snapshot(source: Path, target: Path) -> int:
    managed = {}
    for relative, item in walk(source):
        mark = identity(item)
        if mark is not None and mark == identity(target / relative):
            managed[relative] = mark
    return record_manifest(target, managed)


def clean(target: Path) -> dict:
    path = manifest_path(target)
    data = read_manifest(target, path)
    removed = 0
    retained = []
    for relative, expected in data["entries"].items():
        item = target / relative
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
