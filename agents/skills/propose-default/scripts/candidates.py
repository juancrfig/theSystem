#!/usr/bin/env python3
"""Lists theSystem files in this workspace that differ from the baseline, and copies them into a theSystem tree.

  candidates.py [--workspace <ws>] list
      JSON list of candidates: {"change": "changed"|"added"|"deleted", "path": <workspace path>,
      "repo_path": <path in theSystem>}.
  candidates.py [--workspace <ws>] apply --repo <theSystem worktree> <workspace path>...
      Carries those workspace edits onto the worktree (a three-way merge, since master may have moved on since the
      baseline), or deletes the files there, with install substitutions reversed. "conflict": true means the
      file now has conflict markers to resolve before committing.

The workspace defaults to $THESYSTEM_WORKSPACE, then the current folder. Only theSystem's files are candidates:
the baseline's files plus new files in global agents/. Project folders and .thesystem/ never are.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def load_baseline(workspace: Path) -> tuple[dict, dict[str, bytes]]:
    directory = workspace / ".thesystem" / "baseline"
    if not (directory / "release.json").is_file():
        sys.exit(json.dumps({"status": "error", "code": "NO_BASELINE",
                             "message": "this workspace has no baseline yet; run the company command's update first"}))
    record = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    root = directory / "files"
    return record, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def candidates(workspace: Path) -> list[dict]:
    _, base = load_baseline(workspace)
    found = []
    for name, content in sorted(base.items()):
        local = workspace / name
        if not local.is_file():
            found.append(("deleted", name))
        elif local.read_bytes() != content:
            found.append(("changed", name))
    agents = workspace / "agents"
    for path in sorted(agents.rglob("*")) if agents.is_dir() else []:
        name = path.relative_to(workspace).as_posix()
        # Bytecode comes from running a skill's tests here; it is never a default worth sharing.
        if path.is_file() and name not in base and "__pycache__" not in path.parts and path.suffix != ".pyc":
            found.append(("added", name))
    return [{"change": change, "path": name, "repo_path": repo_path(name)} for change, name in found]


def repo_path(name: str) -> str:
    # The installer seeds the repo's agents/ into the workspace agents/, and the repo's workspace/ into the root.
    return name if name.startswith("agents/") else f"workspace/{name}"


def unsubstitute(name: str, content: bytes, record: dict) -> bytes:
    if name not in record.get("substituted", []):
        return content
    company = re.escape(record["company"].encode())
    return re.sub(rb"(?<![\w-])" + company + rb"(?![\w-])", b"{{COMMAND}}", content)


def merge(current: bytes, base: bytes, mine: bytes) -> tuple[bytes, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for label, content in (("master", current), ("baseline", base), ("workspace", mine)):
            path = Path(tmp) / label
            path.write_bytes(content)
            paths.append(str(path))
        merged = subprocess.run(["git", "merge-file", "-p", "-L", "master", "-L", "baseline", "-L", "workspace",
                                 *paths], capture_output=True)
    return merged.stdout, merged.returncode == 0


def apply(workspace: Path, repo: Path, names: list[str]) -> list[dict]:
    record, base = load_baseline(workspace)
    known = {c["path"]: c for c in candidates(workspace)}
    written = []
    for name in names:
        if name not in known:
            sys.exit(json.dumps({"status": "error", "code": "NOT_A_CANDIDATE", "message": name}))
        target = repo / known[name]["repo_path"]
        entry = {**known[name], "conflict": False}
        if entry["change"] == "deleted":
            target.unlink(missing_ok=True)
        else:
            source = workspace / name
            mine = unsubstitute(name, source.read_bytes(), record)
            # master may have moved on since the baseline release: carry only the workspace's own edit onto it,
            # so the proposal never reverts newer theSystem work.
            if target.is_file():
                old = unsubstitute(name, base.get(name, b""), record)
                mine, clean = merge(target.read_bytes(), old, mine)
                entry["conflict"] = not clean
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(mine)
            target.chmod(source.stat().st_mode & 0o777)
        written.append(entry)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=os.environ.get("THESYSTEM_WORKSPACE") or ".")
    parser.add_argument("action", choices=("list", "apply"))
    parser.add_argument("--repo", type=Path)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_intermixed_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if args.action == "list":
        print(json.dumps({"status": "ok", "candidates": candidates(workspace)}, indent=2))
        return 0
    if not args.repo or not args.paths:
        parser.error("apply needs --repo and at least one path")
    print(json.dumps({"status": "ok", "applied": apply(workspace, args.repo.resolve(), args.paths)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
