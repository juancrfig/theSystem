"""CLI entry point for the standalone theSystem workspace installer."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys

from thesystem.setup.workflow import (
    LifecycleError,
    _has_git_root,
    _install_alias,
    _install_global_command,
    _seed_missing_context_files,
    _selected_profile,
    _source_root,
    _validate_workspace,
    configure,
    doctor,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="install",
        description="Unified workspace installer and Hermes environment wiring for theSystem.",
    )
    parser.add_argument("workspace_pos", nargs="?", metavar="WORKSPACE", help="Target workspace directory or company name")
    parser.add_argument("company_pos", nargs="?", metavar="COMPANY", help="Company alias name")
    parser.add_argument("-w", "--workspace", help="Target workspace directory (default: ~/workspace)")
    parser.add_argument("-c", "--company", help="Company alias name (default: workspace)")
    parser.add_argument(
        "-r", "--runtime", choices=["none", "hermes"], default="none",
        help="Runtime mode: 'none' (default, infrastructure only) or 'hermes'",
    )
    parser.add_argument("-p", "--profile", help="Hermes profile name (default: active profile or 'master')")
    parser.add_argument(
        "--non-interactive", dest="non_interactive", action="store_true", default=False,
        help="Run non-interactively without prompting",
    )
    parser.add_argument(
        "--interactive", dest="non_interactive", action="store_false",
        help="Run interactively and prompt for configuration (default)",
    )
    parser.add_argument("--experimental", action="store_true", help="Include experimental rules")
    parser.add_argument("--json", action="store_true", help="Output doctor report as JSON")
    return parser.parse_args(argv)


def derive_company_name(workspace: Path) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", workspace.name)
    if cleaned and re.match(r"[A-Za-z]", cleaned):
        return cleaned.lower()
    return "workspace"


def prompt_company_name(default: str = "workspace") -> str:
    prompt_text = "Company name: "
    if sys.stdout.isatty():
        if sys.stdin.isatty():
            try:
                sys.stdout.write(prompt_text)
                sys.stdout.flush()
                entered = sys.stdin.readline().strip()
                return entered or default
            except (EOFError, KeyboardInterrupt):
                sys.stderr.write("\ninstall: aborted\n")
                raise

        try:
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                line = sys.stdin.readline()
                if line and line.strip():
                    return line.strip()
        except (OSError, ValueError):
            pass

        try:
            with open("/dev/tty", "r") as tty_in:
                sys.stdout.write(prompt_text)
                sys.stdout.flush()
                entered = tty_in.readline().strip()
                return entered or default
        except (OSError, IOError):
            pass

    try:
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r:
            line = sys.stdin.readline()
            if line and line.strip():
                return line.strip()
    except (OSError, ValueError):
        pass

    return default


def main(argv=None):
    args = parse_args(argv)
    non_interactive = args.non_interactive

    workspace_arg = args.workspace or args.workspace_pos
    company_arg = args.company or args.company_pos

    workspace = None
    company = None

    if workspace_arg:
        expanded = Path(workspace_arg).expanduser()
        if expanded.is_dir() or "/" in workspace_arg or workspace_arg.startswith("."):
            workspace = expanded.resolve()
        else:
            if not company_arg:
                company_arg = workspace_arg

    if company_arg:
        company = company_arg.strip()

    if not non_interactive and not company:
        try:
            company = prompt_company_name()
        except (EOFError, KeyboardInterrupt):
            return 1

    if workspace is None:
        target_dir = Path.home() / "workspace"
        if not target_dir.exists() and not target_dir.is_symlink():
            target_dir.mkdir(parents=True, exist_ok=True)
        workspace = target_dir.resolve()
    else:
        if not workspace.exists() and not workspace.is_symlink():
            workspace.mkdir(parents=True, exist_ok=True)

    if not company:
        company = derive_company_name(workspace)

    cleaned = re.sub(r"[^A-Za-z0-9]", "", company)
    if not cleaned or not re.match(r"[A-Za-z]", cleaned):
        sys.stderr.write(f"install: company alias must match [A-Za-z][A-Za-z0-9]*, got: {company!r}\n")
        return 1

    command_name = company_arg if (company_arg and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", company_arg)) else cleaned.lower()

    if args.runtime == "hermes" and not _has_git_root(workspace):
        try:
            subprocess.run(["git", "-C", str(workspace), "init", "-q"], check=True)
        except (OSError, subprocess.CalledProcessError):
            pass

    source = _source_root()

    try:
        workspace = _validate_workspace(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        # 1. Hard prerequisite: ensure the global CLI is installed
        _install_global_command(source, experimental=args.experimental)

        # 2. Context seeding
        seeded = _seed_missing_context_files(source, workspace)

        # 3. Company alias
        _install_alias(command_name, workspace)

        # 4. Workspace wiring (Protocol 1: configure)
        selected_profile = _selected_profile(args.profile)
        configure(
            workspace=workspace,
            runtime=args.runtime,
            profile=selected_profile,
            non_interactive=non_interactive,
        )

        if not args.json:
            print(f"✓ Installed theSystem global CLI in {Path.home() / '.local/bin/thesystem'}")
            print(f"✓ Created company alias '{command_name}' in {Path.home() / '.local/bin' / command_name}")
            if seeded:
                print(f"✓ Seeded canonical files: {', '.join(seeded)}")
            print(f"✓ Configured workspace: {workspace} (runtime: {args.runtime})")

        if args.json:
            return doctor(workspace, runtime=args.runtime, profile=selected_profile)

        # 5. Doctor check (silent verification for standard install)
        with redirect_stdout(io.StringIO()):
            return doctor(workspace, runtime=args.runtime, profile=selected_profile)

    except LifecycleError as error:
        if args.json:
            print(json.dumps({"status": "error", "code": error.code, "message": str(error)}))
        else:
            sys.stderr.write(f"theSystem: {error.code}: {error}\n")
        return 1
    except Exception as error:
        if args.json:
            print(json.dumps({"status": "error", "code": "INSTALL_FAILED", "message": str(error)}))
        else:
            sys.stderr.write(f"theSystem: INSTALL_FAILED: {error}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
