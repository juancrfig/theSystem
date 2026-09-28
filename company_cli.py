#!/usr/bin/env python3
"""Installed per-company command for theSystem workspaces."""
from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Orchestrator is imported lazily so registration remains usable in a minimal
# installed distribution that predates the optional execution module.

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
EXIT_ERROR = 1
EXIT_USAGE = 2
# Distribution-owned workspace paths cannot be registered as projects.
RESERVED_WORKSPACE_NAMES = {
    ".git", ".thesystem", ".agents", ".githooks", "AGENTS.md", "CONTEXT.md",
    "README.md", "agents", "bootstrap", "company_cli.py", "docs", "install",
    "tests", "tickets", "wiki",
}
PROJECT_INFRASTRUCTURE = ("wiki", "agents", "tickets")


class ProjectError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def fail(code: str, message: str, status: int = EXIT_ERROR) -> int:
    emit({"status": "error", "code": code, "message": message})
    return status


def workspace_path() -> Path:
    value = os.environ.get("THESYSTEM_WORKSPACE")
    if not value:
        raise ValueError("THESYSTEM_WORKSPACE is required; the company command is not bound to a workspace")
    workspace = Path(value).expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace is not an existing directory: {value}")
    return workspace


def usage() -> str:
    return "Usage: COMPANY [--help|--json] [add-project PATH|orchestrator ACTION ...]"


def run_orchestrator(args: list[str]) -> int:
    """Run an orchestrator action while preserving the company's JSON error contract."""
    try:
        if args and args[0] == "orchestrator":
            args = args[1:]
        if "--project" not in args:
            return fail("PROJECT_REQUIRED", "orchestrator commands require --project PATH", EXIT_USAGE)
        action = args[0] if args else ""
        if action not in {"create-task", "approve", "start", "status", "cancel", "integrate"}:
            return fail("UNKNOWN_COMMAND", f"unknown orchestrator command: {action}", EXIT_USAGE)
        import contextlib
        from io import StringIO
        from the_system_orchestrator import main as orchestrator_main
        # The module's public CLI is intentionally reused so company and direct
        # entry points have identical validation and lifecycle semantics.
        with contextlib.redirect_stdout(StringIO()) as captured:
            code = orchestrator_main(args)
        text = captured.getvalue().strip()
        if text:
            print(text)
        return code
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        return fail("ORCHESTRATOR_UNAVAILABLE", str(exc))


def _lstat(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _registry_entries(registry: Path, workspace: Path) -> list[dict]:
    if _lstat(registry) is None:
        return []
    if registry.is_symlink() or not registry.is_file():
        raise ValueError("project registry is not a regular file")
    try:
        value = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read project registry: {exc}") from exc
    if not isinstance(value, list):
        raise ValueError("project registry is not a list")
    entries: list[dict] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("project registry contains an invalid entry")
        raw_path = Path(item["path"])
        if not raw_path.is_absolute():
            raise ValueError("project registry contains a relative path")
        try:
            registered = raw_path.resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"project registry contains an unreadable path: {raw_path}") from exc
        if not _inside(registered, workspace) or registered == workspace or not registered.is_dir():
            raise ValueError("project registry contains a path outside the workspace")
        entries.append({**item, "path": str(registered)})
    return entries


def _check_project(project: Path, workspace: Path) -> None:
    relative = project.relative_to(workspace)
    if not relative.parts:
        raise ProjectError("PROJECT_IS_WORKSPACE", "workspace itself is not a project")
    if relative.parts[0] in RESERVED_WORKSPACE_NAMES:
        raise ProjectError("PROJECT_RESERVED_PATH", "project path is reserved workspace infrastructure")
    if _lstat(project / ".git") is not None:
        raise ProjectError("PROJECT_IS_SOURCE_CLONE", "project is a source clone (.git exists)")
    for name in PROJECT_INFRASTRUCTURE:
        path = project / name
        info = _lstat(path)
        if info is not None and (path.is_symlink() or not path.is_dir()):
            raise ProjectError("PROJECT_INFRASTRUCTURE_INVALID", f"project infrastructure path is not a real directory: {name}")


def _write_registry(registry: Path, entries: list[dict]) -> None:
    payload = (json.dumps(entries, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix="projects.", suffix=".tmp", dir=registry.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, registry)
        directory_fd = os.open(registry.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def add_project(raw: str, workspace: Path) -> int:
    workspace = workspace.resolve()
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        project = candidate.resolve(strict=True)
        if not project.is_dir():
            return fail("PROJECT_NOT_DIRECTORY", f"project path is not a directory: {raw}")
        if not _inside(project, workspace):
            return fail("PROJECT_OUTSIDE_WORKSPACE", "project must be strictly inside the company workspace")
        try:
            _check_project(project, workspace)
        except ProjectError as exc:
            return fail(exc.code, str(exc))

        registry_dir = workspace / ".thesystem"
        existing_dir = _lstat(registry_dir)
        if existing_dir is not None and (registry_dir.is_symlink() or not registry_dir.is_dir()):
            return fail("REGISTRY_INVALID", "registry directory is not a real directory")
        registry_dir.mkdir(parents=True, exist_ok=True)
        lock_path = registry_dir / "projects.lock"
        lock_info = _lstat(lock_path)
        if lock_info is not None and (lock_path.is_symlink() or not lock_path.is_file()):
            return fail("REGISTRY_INVALID", "registry lock is not a regular file")
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            registry = registry_dir / "projects.json"
            entries = _registry_entries(registry, workspace)
            project_value = str(project)
            matching = [entry for entry in entries if entry["path"] == project_value]
            if not matching:
                for entry in entries:
                    registered = Path(entry["path"])
                    if registered != project and (_inside(project, registered) or _inside(registered, project)):
                        return fail("PROJECT_OVERLAPS_REGISTERED", "project overlaps a registered project")
            created: list[Path] = []
            try:
                for name in PROJECT_INFRASTRUCTURE:
                    path = project / name
                    if _lstat(path) is None:
                        path.mkdir()
                        created.append(path)
                    if path.is_symlink() or not path.is_dir():
                        raise OSError(errno.ELOOP, f"invalid project infrastructure path: {path}")
                already = bool(matching)
                if not already:
                    entries.append({"name": project.name, "path": project_value})
                    _write_registry(registry, entries)
            except Exception:
                for path in reversed(created):
                    try:
                        path.rmdir()
                    except OSError:
                        pass
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except ProjectError as exc:
        return fail(exc.code, str(exc))
    except ValueError as exc:
        return fail("REGISTRY_INVALID" if "registry" in str(exc).lower() else "PROJECT_INVALID", str(exc))
    except OSError as exc:
        return fail("PROJECT_SETUP_FAILED", f"cannot register project: {exc}")
    emit({"status": "ok", "command": "add-project", "project": str(project), "idempotent": bool(matching)})
    return 0


def launch_master(workspace: Path, direct: bool = False, runtime: str | None = None, json_mode: bool = False) -> int:
    selected = runtime or ((workspace / ".thesystem" / "runtime").read_text().strip() if (workspace / ".thesystem" / "runtime").exists() else "hermes")
    if selected not in ("hermes", "copilot"):
        return fail("RUNTIME_NOT_CONFIGURED", "no chat runtime configured")
    env = dict(os.environ, THESYSTEM_WORKSPACE=str(workspace))
    if selected == "copilot" and not any(env.get(k) for k in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")):
        auth = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if auth.returncode or not auth.stdout.splitlines():
            return fail("COPILOT_AUTH_REQUIRED", "GitHub Copilot authentication unavailable")
        env["COPILOT_GITHUB_TOKEN"] = auth.stdout.splitlines()[-1].strip()
    if direct:
        command = ["hermes", "-p", "master"] if selected == "hermes" else ["copilot"]
        try: return subprocess.call(command, cwd=str(workspace), env=env)
        except OSError as exc: return fail("RUNTIME_NOT_AVAILABLE", str(exc))
    if __import__("shutil").which("herdr") is None:
        return fail("HERDR_NOT_AVAILABLE", "Herdr is required for normal launch")
    args=["herdr","workspace","create","--cwd",str(workspace),"--label",workspace.name,"--no-focus"]
    # Herdr's --env option embeds the value in command-line arguments visible
    # to other local processes. Never put a provider credential on that path.
    created=subprocess.run(args,capture_output=True,text=True,timeout=20,env=env)
    if created.returncode:
        return fail("HERDR_WORKSPACE_FAILED", "Herdr could not create the workspace")
    try:
        result=json.loads(created.stdout.splitlines()[-1])["result"]
        pane=result["root_pane"]["pane_id"]; workspace_id=result["workspace"]["workspace_id"]
    except (ValueError,IndexError,KeyError,TypeError):
        return fail("HERDR_RESPONSE_INVALID", "Herdr returned no workspace or pane ID")
    launch=["herdr","agent","start",selected,"--kind",selected,"--pane",pane,"--timeout","15000"]
    if selected=="hermes": launch.extend(["--","-p","master"])
    started=subprocess.run(launch,capture_output=True,text=True,timeout=25,env=env)
    status="started" if started.returncode==0 else "awaiting-interaction"
    if started.returncode and "agent_not_ready" not in (started.stdout+started.stderr):
        subprocess.run(["herdr","workspace","close",workspace_id],capture_output=True,text=True,timeout=10)
        return fail("HERDR_AGENT_FAILED", "Herdr could not launch the selected agent")
    if json_mode or not sys.stdin.isatty():
        emit({"status":status,"runtime":selected,"workspace_id":workspace_id,"pane_id":pane})
        return 0
    subprocess.run(["herdr","workspace","focus",workspace_id],capture_output=True,text=True,timeout=10)
    return subprocess.call(["herdr"],cwd=str(workspace),env=env)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in args
    args = [arg for arg in args if arg != "--json"]
    if any(arg in ("-h", "--help") for arg in args):
        if json_mode:
            emit({"status": "ok", "help": usage()})
        else:
            print(usage())
        return 0
    if json_mode and not args:
        return fail("JSON_COMMAND_REQUIRED", "--json requires a non-interactive command", EXIT_USAGE)
    if args and (args[0] == "orchestrator" or args[0] in {"create-task", "approve", "start", "status", "cancel", "integrate"}):
        return run_orchestrator(args)
    if args and args[0] == "add-project":
        if len(args) != 2 or not args[1]:
            return fail("MISSING_ARGUMENT", "add-project requires PATH", EXIT_USAGE)
        try:
            workspace = workspace_path()
        except ValueError as exc:
            return fail("WORKSPACE_NOT_BOUND", str(exc))
        return add_project(args[1], workspace)
    if args and args not in (["launch"],["--direct"]):
        return fail("UNKNOWN_COMMAND", f"unknown command: {args[0]}", EXIT_USAGE)
    try:
        workspace = workspace_path()
    except ValueError as exc:
        return fail("WORKSPACE_NOT_BOUND", str(exc))
    if args not in ([],["launch"],["--direct"]): return fail("UNKNOWN_COMMAND", f"unknown command: {args[0]}", EXIT_USAGE)
    return launch_master(workspace,direct=args==["--direct"],json_mode=json_mode)


if __name__ == "__main__":
    raise SystemExit(main())
