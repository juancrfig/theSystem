"""Public command router for distribution, workspace setup, and workspace operations."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from thesystem.cli import main as workspace_main
from thesystem.setup.workflow import LifecycleError, _hermes_target, doctor, install, rollback, uninstall, upgrade, configure


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="thesystem", description="Manage theSystem distributions and workspaces")
    commands = result.add_subparsers(dest="command")
    setup = commands.add_parser("install", help="install distribution files and configure a workspace")
    setup.add_argument("--json", action="store_true")
    setup.add_argument("--workspace")
    setup.add_argument("--runtime", choices=("hermes", "none"), default="hermes")
    setup.add_argument("--profile")
    setup.add_argument("--company")
    setup.add_argument("--non-interactive", action="store_true")
    setup.add_argument("--experimental", action="store_true")
    for name in ("configure", "doctor"):
        setup = commands.add_parser(name, help=f"{name.capitalize()} an existing workspace")
        setup.add_argument("--json", action="store_true")
        setup.add_argument("--workspace")
        setup.add_argument("--runtime", choices=("hermes", "none"), default=None if name == "doctor" else "hermes")
        setup.add_argument("--profile")
        if name == "configure":
            setup.add_argument("--development", action="store_true")
            setup.add_argument("--non-interactive", action="store_true")
    for name in ("upgrade", "rollback", "uninstall"):
        setup = commands.add_parser(name, help=f"{name.capitalize()} the installed distribution")
        setup.add_argument("--json", action="store_true")
        setup.add_argument("--workspace")
        if name == "upgrade":
            setup.add_argument("--runtime", choices=("hermes", "none"))
            setup.add_argument("--profile")
            setup.add_argument("--experimental", action="store_true")
            setup.add_argument("--non-interactive", action="store_true")
    return result


def _workspace(args: argparse.Namespace, required: bool = True) -> Path | None:
    value = getattr(args, "workspace", None) or os.environ.get("THESYSTEM_WORKSPACE")
    if not value:
        if required:
            raise LifecycleError("WORKSPACE_REQUIRED", "--workspace is required when no workspace binding is available")
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] in ("-h", "--help"):
        parser().print_help()
        return 0
    if raw[0] not in {"install", "configure", "doctor", "upgrade", "rollback", "uninstall"}:
        workspace = None
        filtered = []
        index = 0
        while index < len(raw):
            if raw[index] == "--workspace":
                if index + 1 == len(raw):
                    print("thesystem: --workspace requires a path", file=sys.stderr)
                    return 2
                workspace = raw[index + 1]
                index += 2
            else:
                filtered.append(raw[index])
                index += 1
        env = dict(os.environ)
        if workspace:
            env["THESYSTEM_WORKSPACE"] = workspace
        os.environ.update({"THESYSTEM_WORKSPACE": workspace} if workspace else {})
        return workspace_main(filtered)

    args = parser().parse_args(raw)
    operation_result = None
    try:
        workspace = _workspace(args)
        if workspace is None:
            raise LifecycleError("WORKSPACE_REQUIRED", "--workspace is required")
        if args.command == "install":
            install(workspace, args.runtime, args.profile, args.company, args.experimental, args.non_interactive)
        elif args.command == "configure":
            if workspace is None:
                raise LifecycleError("WORKSPACE_REQUIRED", "--workspace is required when no workspace binding is available")
            configure(workspace, args.runtime, args.profile, args.development, args.non_interactive)
        elif args.command == "doctor":
            if workspace is None:
                raise LifecycleError("WORKSPACE_REQUIRED", "--workspace is required when no workspace binding is available")
            return doctor(workspace, args.runtime, args.profile)
        elif args.command == "upgrade":
            upgrade(workspace, args.experimental, args.non_interactive, args.runtime, args.profile)
        elif args.command == "rollback":
            operation_result = rollback(workspace)
        else:
            operation_result = uninstall(workspace)
    except LifecycleError as error:
        if args.json:
            import json
            print(json.dumps({"status": "error", "code": error.code, "message": str(error)}, sort_keys=True))
        else:
            print(f"theSystem: {error.code}: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        if args.json:
            import json
            print(json.dumps({"status": "error", "code": "SETUP_FAILED", "message": str(error)}, sort_keys=True))
        else:
            print(f"theSystem: setup failed: {error}", file=sys.stderr)
        return 1
    if args.command != "doctor":
        if args.json:
            import json
            runtime = getattr(args, "runtime", None)
            if args.command == "upgrade" and runtime is None:
                runtime_file = workspace / ".thesystem/runtime"
                runtime = runtime_file.read_text(encoding="utf-8").strip() if runtime_file.is_file() else None
            profile = getattr(args, "profile", None)
            if args.command == "upgrade" and profile is None:
                profile_file = workspace / ".thesystem/profile"
                profile = profile_file.read_text(encoding="utf-8").strip() if profile_file.is_file() else None
            selected_profile = _hermes_target(profile).profile if runtime == "hermes" else None
            payload = {"status": "ok", "command": args.command, "workspace": str(workspace),
                       "runtime": runtime, "profile": selected_profile}
            if operation_result is not None:
                payload.update(operation_result)
            print(json.dumps(payload, sort_keys=True))
        else:
            runtime = getattr(args, "runtime", None)
            if args.command == "upgrade" and runtime is None:
                runtime_file = workspace / ".thesystem/runtime"
                runtime = runtime_file.read_text(encoding="utf-8").strip() if runtime_file.is_file() else None
            profile = getattr(args, "profile", None)
            if args.command == "upgrade" and profile is None:
                profile_file = workspace / ".thesystem/profile"
                profile = profile_file.read_text(encoding="utf-8").strip() if profile_file.is_file() else None
            selected_profile = _hermes_target(profile).profile if runtime == "hermes" else None
            suffix = f" (runtime {runtime}" + (f", Hermes profile {selected_profile}" if selected_profile else "") + ")" if runtime else ""
            if args.command == "rollback" and operation_result is not None:
                readiness = operation_result["readiness"]
                ready = "ready" if readiness.get("ready") else "not ready"
                print(f"theSystem: rollback restored software for {workspace}; Hermes readiness {ready} (exit {operation_result['readiness_exit_code']})")
            else:
                print(f"theSystem: {args.command} completed for {workspace}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
