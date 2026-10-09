"""The workspace command (named after the company at install time). Used by agents; output is JSON.

Tasks are not run by this command: the main agent delegates each task to worker and reviewer subagents itself
(the `run-tasks` skill). The command only keeps the workspace on the latest theSystem release of its channel.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from thesystem import update
from thesystem.errors import CodedError

HELP = """\
usage: {prog} <command>

  update        install the latest theSystem release of this channel and merge its files into the workspace
"""


def command_update(workspace: Path) -> dict:
    company = os.environ.get("THESYSTEM_COMMAND")
    if not company:
        raise CodedError("USAGE", "no company command configured; run update through the installed command")
    clone = Path(os.environ.get("THESYSTEM_CLONE") or Path.home() / "theSystem")
    current = update.baseline(workspace)
    from_tag = current[0]["tag"] if current else None
    report = {"status": "ok", "up_to_date": False, "from": from_tag, "to": from_tag, "release_notes": [],
              "updated": [], "added": [], "removed": [], "merged": [], "conflicts": [], "baseline_recorded": False}
    waiting = update.pending(workspace)
    if waiting:
        # The conflicts of the last update come first: until they are resolved, the baseline must stay the old
        # release, or an unresolved conflict would later look like a local edit.
        left = update.unresolved(workspace, waiting["conflicts"])
        if not left:
            update.promote_pending(workspace)
        return {**report, "to": waiting["tag"], "conflicts": left, "baseline_recorded": not left}
    if not (clone / ".git").exists():
        raise CodedError("NO_CLONE", f"no theSystem clone at {clone}; run the installer again")
    latest, revision = update.latest_release(clone)
    if from_tag == latest:
        return {**report, "up_to_date": True}
    package_root = str(Path(__file__).resolve().parents[1])
    with tempfile.TemporaryDirectory() as release:
        update.export(clone, revision, Path(release))
        # The release's own installer re-applies the silent steps and replaces the installed program, so the
        # merge below already runs the new release's code.
        installed = subprocess.run(
            ["bash", str(Path(release) / "install"), "--release", latest, "--update"], capture_output=True,
            text=True, stdin=subprocess.DEVNULL,
            env={**os.environ, "THESYSTEM_WORKSPACE": str(workspace), "THESYSTEM_COMPANY": company,
                 "THESYSTEM_CLONE": str(clone)})
        if installed.returncode:
            raise CodedError("INSTALL_FAILED", (installed.stderr or installed.stdout).strip())
        merged = subprocess.run(
            [sys.executable, "-m", "thesystem.update", "merge", "--source", release, "--workspace", str(workspace),
             "--company", company, "--release", latest, "--clone", str(clone), *(["--from", from_tag] if from_tag else [])],
            capture_output=True, text=True, cwd=package_root, env={**os.environ, "PYTHONPATH": package_root})
    try:
        result = json.loads(merged.stdout)
    except json.JSONDecodeError:
        raise CodedError("MERGE_FAILED", (merged.stderr or merged.stdout).strip()) from None
    if result.get("status") != "ok":
        raise CodedError(result.get("code", "MERGE_FAILED"), result.get("message", ""))
    return result


def main(argv: list[str] | None = None) -> int:
    prog = os.environ.get("THESYSTEM_COMMAND", "thesystem")
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--workspace", default=os.environ.get("THESYSTEM_WORKSPACE"))
    parser.add_argument("command", nargs="?")
    args, extra = parser.parse_known_args(argv)
    if args.command in (None, "-h", "--help", "help"):
        print(HELP.format(prog=prog), end="")
        return 0
    try:
        if extra or not args.workspace:
            raise CodedError("USAGE", "unexpected arguments" if extra else "no workspace configured")
        workspace = Path(args.workspace).expanduser().resolve()
        if args.command != "update":
            raise CodedError("USAGE", HELP.format(prog=prog).strip())
        result = command_update(workspace)
    except CodedError as error:
        print(json.dumps({"status": "error", "code": error.code, "message": error.message}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
