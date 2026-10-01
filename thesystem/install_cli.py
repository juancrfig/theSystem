"""CLI entry point for the standalone theSystem workspace installer."""
import argparse
import json
import os
from pathlib import Path
import re
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
    parser.add_argument("-w", "--workspace", help="Target workspace directory")
    parser.add_argument("-c", "--company", help="Company alias name")
    parser.add_argument(
        "-r", "--runtime", choices=["hermes", "none"], default="hermes",
        help="Runtime mode: 'hermes' (default) or 'none' (infrastructure only)",
    )
    parser.add_argument("-p", "--profile", help="Hermes profile name (default: active profile or 'master')")
    parser.add_argument(
        "--non-interactive", dest="non_interactive", action="store_true", default=None,
        help="Run non-interactively",
    )
    parser.add_argument("--interactive", dest="non_interactive", action="store_false", help="Run interactively")
    parser.add_argument("--experimental", action="store_true", help="Include experimental rules")
    parser.add_argument("--json", action="store_true", help="Output doctor report as JSON")
    return parser.parse_args(argv)


def derive_company_name(workspace: Path) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", workspace.name)
    if cleaned and re.match(r"[A-Za-z]", cleaned):
        return cleaned.lower()
    return "company"


def main(argv=None):
    args = parse_args(argv)
    non_interactive = args.non_interactive if args.non_interactive is not None else not sys.stdin.isatty()

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

    if not company:
        if sys.stdin.isatty():
            try:
                sys.stdout.write("Company name: ")
                sys.stdout.flush()
                company = sys.stdin.readline().strip()
            except (EOFError, KeyboardInterrupt):
                sys.stderr.write("\ninstall: aborted\n")
                return 1
        else:
            line = sys.stdin.readline()
            if line:
                company = line.strip()

    if not company and workspace is not None:
        company = derive_company_name(workspace)

    if not company:
        sys.stderr.write("install: company name is required (pass as argument or via --company)\n")
        return 2

    cleaned = re.sub(r"[^A-Za-z0-9]", "", company)
    if not cleaned or not re.match(r"[A-Za-z]", cleaned):
        sys.stderr.write(f"install: company alias must match [A-Za-z][A-Za-z0-9]*, got: {company!r}\n")
        return 1

    command_name = company_arg if (company_arg and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", company_arg)) else cleaned.lower()

    if workspace is None:
        target_dir = Path.home() / cleaned.lower()
        if not target_dir.exists() and not target_dir.is_symlink():
            target_dir.mkdir(parents=True, exist_ok=True)
        workspace = target_dir.resolve()
    else:
        if not workspace.exists() and not workspace.is_symlink():
            workspace.mkdir(parents=True, exist_ok=True)

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

        # 2. Context seeding per ADR 0002
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
                print(f"✓ Seeded missing context files (ADR 0002): {', '.join(seeded)}")
            print(f"✓ Configured workspace: {workspace} (runtime: {args.runtime})")
            print("\nRunning readiness diagnostics...")

        # 5. Doctor check
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
