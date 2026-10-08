"""Releases, baselines and workspace updates (F10). Standard library only.

  python3 -m thesystem.update seed --source <tree> --workspace <ws> --company <name> --release <tag>
      Called by the installer: adds missing theSystem files and records the baseline of a clean install.
  python3 -m thesystem.update merge --source <tree> --workspace <ws> --company <name> --release <tag>
                                   --clone <clone> [--from <tag>]
      Called by `update` after the new release's installer ran: merges the release's files into the workspace
      and prints the JSON result.

The workspace's theSystem files are exactly the repo's `workspace/` (into the workspace root) and `agents/`
(into the workspace `agents/`). The baseline is `.thesystem/baseline/`: `release.json` plus `files/`, a copy of
those files as the release shipped them, after substitutions. It is the merge base for updates and the
comparison point for proposals.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from thesystem.errors import CodedError

# Workspace paths whose {{COMMAND}} becomes the company command. The propose-default skill reverses it.
SUBSTITUTED = ("AGENTS.md",)
# Releases are vMAJOR.MINOR; the older vMAJOR.MINOR.PATCH tags stay valid and sort among them (v0.2.0 < v0.3).
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)(?:\.(\d+))?$")
MARKER = re.compile(rb"^(<<<<<<<|>>>>>>>)( |$)", re.MULTILINE)

Files = dict[str, tuple[bytes, int]]  # workspace path -> (content, mode)


def release_files(source: Path, company: str) -> Files:
    files: Files = {}
    for folder, prefix in (("workspace", ""), ("agents", "agents/")):
        root = source / folder
        for path in sorted(root.rglob("*")):
            # Bytecode appears in a working tree once a skill's tests ran; it was never shipped.
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            name = prefix + path.relative_to(root).as_posix()
            content = path.read_bytes()
            if name in SUBSTITUTED:
                content = content.replace(b"{{COMMAND}}", company.encode())
            files[name] = (content, path.stat().st_mode & 0o777)
    return files


def _state(workspace: Path) -> Path:
    path = workspace / ".thesystem"
    path.mkdir(exist_ok=True)
    # State is per server; the self-ignoring file keeps it out of the workspace's git without editing .gitignore.
    ignore = path / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return path


def _write(path: Path, content: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_bytes(content)
    if mode is not None:
        path.chmod(mode)


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _save_release(directory: Path, record: dict, files: Files) -> None:
    """Writes `directory` whole, so a crash never leaves half a baseline that looks complete."""
    staging = Path(tempfile.mkdtemp(dir=directory.parent, prefix=f".{directory.name}-"))
    for name, (content, mode) in files.items():
        _write(staging / "files" / name, content, mode)
    (staging / "release.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if directory.exists():
        shutil.rmtree(directory)
    staging.rename(directory)


def record_baseline(workspace: Path, tag: str, company: str, files: Files) -> None:
    record = {"tag": tag, "company": company, "substituted": list(SUBSTITUTED)}
    _save_release(_state(workspace) / "baseline", record, files)
    pending = workspace / ".thesystem" / "pending"
    if pending.exists():
        shutil.rmtree(pending)


def baseline(workspace: Path) -> tuple[dict, dict[str, bytes]] | None:
    directory = workspace / ".thesystem" / "baseline"
    if not (directory / "release.json").is_file():
        return None
    record = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    root = directory / "files"
    copies = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    return record, copies


def seed(source: Path, workspace: Path, company: str, tag: str) -> None:
    files = release_files(source, company)
    for name, (content, mode) in files.items():
        target = workspace / name
        if not os.path.lexists(target):
            _write(target, content, mode)
    # Only a workspace that holds exactly this release can call it its baseline. Anything else (an install
    # from before baselines, or local edits) is adopted by `update`, which reports the differences.
    if baseline(workspace) is None and all(_read(workspace / name) == content for name, (content, _) in files.items()):
        record_baseline(workspace, tag, company, files)


def _conflict_text(local: bytes | None, theirs: bytes | None, tag: str) -> bytes:
    def side(content: bytes | None) -> bytes:
        content = content or b""
        return content if not content or content.endswith(b"\n") else content + b"\n"
    return (b"<<<<<<< workspace\n" + side(local) + b"=======\n" + side(theirs)
            + f">>>>>>> {tag}\n".encode())


def _merge_file(local: bytes, base: bytes, theirs: bytes, base_tag: str, tag: str) -> tuple[bytes, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, content in (("local", local), ("base", base), ("theirs", theirs)):
            path = Path(tmp) / name
            path.write_bytes(content)
            paths.append(str(path))
        merged = subprocess.run(["git", "merge-file", "-p", "-L", "workspace", "-L", f"baseline {base_tag}",
                                 "-L", tag, *paths], capture_output=True)
    if merged.returncode < 0 or merged.returncode > 127:
        raise CodedError("MERGE_FAILED", merged.stderr.decode(errors="replace").strip())
    return merged.stdout, merged.returncode == 0


def merge(source: Path, workspace: Path, company: str, tag: str) -> dict:
    theirs_files = release_files(source, company)
    current = baseline(workspace)
    base_tag, base = (current[0]["tag"], current[1]) if current else ("none", {})
    result: dict = {"updated": [], "added": [], "removed": [], "merged": [], "conflicts": []}
    for name in sorted(set(theirs_files) | set(base)):
        path = workspace / name
        old = base.get(name)
        local = _read(path)
        theirs, mode = theirs_files.get(name, (None, None))
        if local == theirs or theirs == old:
            continue  # already the release's version, or only the workspace changed it: keep the workspace
        if local == old:
            if theirs is None:
                path.unlink()
                _prune(path.parent, workspace)
                result["removed"].append(name)
            else:
                _write(path, theirs, mode)
                result["added" if local is None else "updated"].append(name)
            continue
        if local is not None and old is not None and theirs is not None:
            content, clean = _merge_file(local, old, theirs, base_tag, tag)
            _write(path, content)
            if clean:
                result["merged"].append(name)
                continue
            reason = "both changed"
        else:
            # One side is missing, so there is nothing to merge line by line: show both versions whole.
            _write(path, _conflict_text(local, theirs, tag), mode)
            reason = ("removed upstream, changed locally" if theirs is None
                      else "removed locally, changed upstream" if local is None
                      else "differs from the release" if not current
                      else "added upstream, a different local file exists")
        result["conflicts"].append({"path": name, "reason": reason})
    if result["conflicts"]:
        record = {"tag": tag, "company": company, "substituted": list(SUBSTITUTED), "conflicts": result["conflicts"]}
        _save_release(_state(workspace) / "pending", record, theirs_files)
        result["baseline_recorded"] = False
    else:
        record_baseline(workspace, tag, company, theirs_files)
        result["baseline_recorded"] = True
    return result


def _prune(directory: Path, workspace: Path) -> None:
    # A removed skill must not leave an empty folder that still looks like a skill.
    while directory != workspace and directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()
        directory = directory.parent


def pending(workspace: Path) -> dict | None:
    path = workspace / ".thesystem" / "pending" / "release.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def unresolved(workspace: Path, conflicts: list[dict]) -> list[dict]:
    """A conflict is resolved once its file has no conflict markers, or was deleted."""
    return [c for c in conflicts if MARKER.search(_read(workspace / c["path"]) or b"")]


def promote_pending(workspace: Path) -> None:
    state = workspace / ".thesystem"
    record = json.loads((state / "pending" / "release.json").read_text(encoding="utf-8"))
    record.pop("conflicts", None)
    (state / "pending" / "release.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if (state / "baseline").exists():
        shutil.rmtree(state / "baseline")
    (state / "pending").rename(state / "baseline")


# Release source: the server's clone of theSystem. Read through git only, so its branch and files stay untouched.

def git(clone: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True)
    if done.returncode:
        raise CodedError("GIT_FAILED", (done.stderr or done.stdout).strip())
    return done.stdout


def release_tags(clone: Path) -> list[str]:
    tags = [tag for tag in git(clone, "tag", "-l", "v*").split() if RELEASE_TAG.match(tag)]
    return sorted(tags, key=_version)


def _version(tag: str) -> tuple[int, ...]:
    return tuple(int(part or 0) for part in RELEASE_TAG.match(tag).groups())


def export(clone: Path, tag: str, directory: Path) -> None:
    archive = subprocess.Popen(["git", "-C", str(clone), "archive", tag], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    unpack = subprocess.run(["tar", "-x", "-C", str(directory)], stdin=archive.stdout, capture_output=True)
    archive.stdout.close()
    if archive.wait() or unpack.returncode:
        raise CodedError("EXPORT_FAILED", f"could not read release {tag} from {clone}: "
                                          f"{(archive.stderr.read().decode() or unpack.stderr.decode()).strip()}")


def release_notes(clone: Path, from_tag: str | None, to_tag: str) -> list[dict]:
    tags = release_tags(clone)
    if from_tag and RELEASE_TAG.match(from_tag):
        between = [tag for tag in tags if _version(from_tag) < _version(tag) <= _version(to_tag)]
    else:
        between = [to_tag]
    repo = _github_repo(clone)
    return [{"tag": tag, "notes": _github_notes(repo, tag) or _annotation(clone, tag)} for tag in between]


def _github_repo(clone: Path) -> str | None:
    try:
        url = git(clone, "remote", "get-url", "origin").strip()
    except CodedError:
        return None
    found = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return found.group(1) if found else None


def _github_notes(repo: str | None, tag: str) -> str | None:
    if not repo or not shutil.which("gh"):
        return None
    try:
        shown = subprocess.run(["gh", "release", "view", tag, "--repo", repo, "--json", "body", "--jq", ".body"],
                               capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    if shown.returncode:
        return None
    return shown.stdout.strip() or None


def _annotation(clone: Path, tag: str) -> str:
    return git(clone, "tag", "-l", "--format=%(contents)", tag).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m thesystem.update")
    parser.add_argument("action", choices=("seed", "merge"))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--company", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--clone", type=Path)
    parser.add_argument("--from", dest="from_tag")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    if args.action == "seed":
        seed(args.source, workspace, args.company, args.release)
        return 0
    try:
        result = merge(args.source, workspace, args.company, args.release)
        notes = release_notes(args.clone, args.from_tag, args.release) if args.clone else []
    except CodedError as error:
        print(json.dumps({"status": "error", "code": error.code, "message": error.message}))
        return 1
    print(json.dumps({"status": "ok", "up_to_date": False, "from": args.from_tag, "to": args.release,
                      "release_notes": notes, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
