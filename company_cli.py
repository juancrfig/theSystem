#!/usr/bin/env python3
"""Non-chat company command for workspace, task, evidence, and learning operations."""
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

# Installed entry points must not leave unowned caches behind after rollback.
if __name__ == "__main__":
    sys.dont_write_bytecode = True

from thesystem.setup.distribution import MANAGED_ROOTS

# Orchestrator is imported lazily so registration remains usable in a minimal
# installed distribution that predates the optional execution module.

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
EXIT_ERROR = 1
EXIT_USAGE = 2
# Distribution-owned workspace paths cannot be registered as projects.
RESERVED_WORKSPACE_NAMES = {
    *MANAGED_ROOTS, ".git", ".thesystem", ".agents", "tests", "tickets", "wiki",
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
    return ("Usage: COMPANY [--help|--json] "
            "[add-project PATH|add-source-clone PROJECT CLONE|set-role PROJECT ROLE [OPTIONS]|"
            "retry --project PATH --task ID|evidence --project PATH --run ID|"
            "learning inventory|show|decide ...|orchestrator ACTION ...]")


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
        if action == "create-task":
            project_raw = _option_value(args, "--project")
            clone_raw = _option_value(args, "--source-clone")
            if not clone_raw:
                return fail("SOURCE_CLONE_REQUIRED", "create-task requires --source-clone PATH", EXIT_USAGE)
            try:
                workspace = workspace_path()
                project = _registered_project(project_raw or "", workspace)
                clone = Path(clone_raw).expanduser().resolve(strict=True)
                sources = _registry_entries(workspace / ".thesystem" / "source-clones.json", workspace)
                if {"project": str(project), "path": str(clone)} not in sources:
                    return fail("SOURCE_CLONE_NOT_REGISTERED", "register the source clone for this project before creating a task", EXIT_USAGE)
            except ProjectError as exc:
                return fail(exc.code, str(exc), EXIT_USAGE)
            except (OSError, ValueError) as exc:
                return fail("SOURCE_CLONE_REGISTRY_INVALID", str(exc), EXIT_USAGE)
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


def _write_registry(registry: Path, entries: list[dict] | dict) -> None:
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


def _registered_project(raw: str, workspace: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    project = candidate.resolve(strict=True)
    entries = _registry_entries(workspace / ".thesystem" / "projects.json", workspace)
    if str(project) not in {entry["path"] for entry in entries}:
        raise ProjectError("PROJECT_NOT_REGISTERED", "project must be registered before this operation")
    return project


def add_source_clone(raw_project: str, raw_clone: str, workspace: Path) -> int:
    """Register an existing Git clone beneath one registered project."""
    try:
        project = _registered_project(raw_project, workspace)
        candidate = Path(raw_clone).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        clone = candidate.resolve(strict=True)
        if not clone.is_dir() or _lstat(clone / ".git") is None:
            return fail("SOURCE_CLONE_INVALID", "source clone must be an existing Git working tree")
        if not _inside(clone, project) or clone == project:
            return fail("SOURCE_CLONE_OUTSIDE_PROJECT", "source clone must be strictly inside its registered project")
        registry_dir = workspace / ".thesystem"
        registry = registry_dir / "source-clones.json"
        with open(registry_dir / "projects.lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            entries = _registry_entries(registry, workspace) if _lstat(registry) else []
            project_paths = {item["path"] for item in _registry_entries(workspace / ".thesystem" / "projects.json", workspace)}
            for entry in entries:
                registered_project = entry.get("project")
                registered_clone = Path(entry["path"])
                if (not isinstance(registered_project, str) or
                        registered_project not in project_paths or
                        not _inside(registered_clone, Path(registered_project)) or registered_clone == Path(registered_project)):
                    raise ValueError("source clone registry contains an invalid entry")
            record = {"project": str(project), "path": str(clone)}
            already = record in entries
            if not already:
                entries.append(record)
                _write_registry(registry, entries)
            fcntl.flock(lock, fcntl.LOCK_UN)
    except ProjectError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE if exc.code == "PROJECT_NOT_REGISTERED" else EXIT_ERROR)
    except (OSError, ValueError) as exc:
        return fail("SOURCE_CLONE_REGISTRY_INVALID", str(exc))
    emit({"status": "ok", "command": "add-source-clone", "project": str(project),
          "source_clone": str(clone), "idempotent": already})
    return 0


def _safe_role_value(value: str, kind: str) -> str:
    if not value or "\x00" in value:
        raise ProjectError("ROLE_INVALID", f"{kind} must not be empty")
    if kind in {"rules", "skills", "tools", "utils"}:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ProjectError("ROLE_INVALID", f"{kind} entries must be relative paths inside project guidance")
    return value


def set_role(raw_project: str, role: str, options: list[str], workspace: Path) -> int:
    try:
        project = _registered_project(raw_project, workspace)
        if not NAME_RE.fullmatch(role):
            raise ProjectError("ROLE_INVALID", "role must use letters and numbers and start with a letter")
        flags = {"--rule": "rules", "--skill": "skills", "--tool": "tools", "--util": "utils",
                 "--cli": "clis", "--mcp": "mcp_servers"}
        values: dict[str, list[str]] = {}
        index = 0
        while index < len(options):
            flag = options[index]
            if flag not in flags or index + 1 == len(options) or options[index + 1].startswith("--"):
                return fail("ROLE_USAGE", "set-role options are --rule, --skill, --tool, --util, --cli, or --mcp followed by a value", EXIT_USAGE)
            kind = flags[flag]
            values.setdefault(kind, []).append(_safe_role_value(options[index + 1], kind))
            index += 2
        target = project / "agents" / "roles.yaml"
        if _lstat(target) is not None and (target.is_symlink() or not target.is_file()):
            return fail("ROLE_CONFIG_INVALID", "project roles.yaml is not a regular file")
        if target.exists():
            try:
                document = json.loads(target.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                return fail("ROLE_CONFIG_UNSUPPORTED", "existing roles.yaml is not JSON-compatible YAML; preserve it and edit it manually")
            if not isinstance(document, dict):
                return fail("ROLE_CONFIG_INVALID", "project roles.yaml must contain an object")
        else:
            document = {}
        document[role] = values
        worker = document.get("worker", {})
        reviewer = document.get("reviewer", {})
        worker_rules = worker.get("rules", []) if isinstance(worker, dict) else None
        reviewer_rules = reviewer.get("rules", []) if isinstance(reviewer, dict) else None
        if (not isinstance(worker_rules, list) or not isinstance(reviewer_rules, list) or
                not set(worker_rules).issubset(reviewer_rules)):
            return fail("REVIEWER_RULES_MISSING", "reviewer roles must include every worker rule", EXIT_USAGE)
        _write_registry(target, document)
    except ProjectError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE)
    except (OSError, ValueError) as exc:
        return fail("ROLE_SETUP_FAILED", str(exc))
    emit({"status": "ok", "command": "set-role", "project": str(project), "role": role, "role_config": str(target)})
    return 0


def _option_value(args: list[str], option: str) -> str | None:
    try:
        position = args.index(option)
    except ValueError:
        return None
    return args[position + 1] if position + 1 < len(args) else None


def retry_task(args: list[str], workspace: Path) -> int:
    project_raw, task_id = _option_value(args, "--project"), _option_value(args, "--task")
    if not project_raw or not task_id or len(args) != 4:
        return fail("RETRY_USAGE", "retry requires --project PATH --task ID", EXIT_USAGE)
    try:
        project = _registered_project(project_raw, workspace)
        from the_system_orchestrator import Orchestrator
        orchestrator = Orchestrator(project)
        task = orchestrator.task(task_id)
        runs = [run for run in orchestrator.state["runs"].values() if run.get("task_id") == task_id]
        latest = max(runs, key=lambda run: run.get("finished_at", run.get("started_at", ""))) if runs else None
        retryable = {"changes-requested", "execution-failed", "review-failed", "cancelled", "timeout", "aborted", "infra_blocked", "isolation_violated"}
        if not latest or latest.get("status") not in retryable:
            return fail("RETRY_NOT_ALLOWED", "retry requires a prior failed, cancelled, timed-out, or aborted run", EXIT_USAGE)
        if task.get("approval") != "approved":
            return fail("TASK_NOT_APPROVED", "retry requires an approved task", EXIT_USAGE)
    except ProjectError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE)
    except Exception as exc:
        code = getattr(exc, "code", "RETRY_UNAVAILABLE")
        return fail(code, str(exc), EXIT_USAGE if code == "TASK_NOT_FOUND" else EXIT_ERROR)
    return run_orchestrator(["start", "--project", str(project), "--task", task_id])


def show_evidence(args: list[str], workspace: Path) -> int:
    project_raw, run_id = _option_value(args, "--project"), _option_value(args, "--run")
    if not project_raw or not run_id or len(args) != 4 or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        return fail("EVIDENCE_USAGE", "evidence requires --project PATH --run ID", EXIT_USAGE)
    try:
        project = _registered_project(project_raw, workspace)
        target = project / ".thesystem" / "orchestrator" / "runs" / f"{run_id}.json"
        if _lstat(target) is None:
            return fail("EVIDENCE_NOT_FOUND", "no immutable evidence exists for that run", EXIT_USAGE)
        if target.is_symlink() or not target.is_file():
            return fail("EVIDENCE_INVALID", "run evidence is not a regular file")
        record = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("id") != run_id:
            return fail("EVIDENCE_INVALID", "run evidence does not match the requested run")
    except ProjectError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return fail("EVIDENCE_INVALID", f"cannot read run evidence: {exc}")
    emit({"status": "ok", "command": "evidence", "project": str(project), "run": record})
    return 0


def learning(args: list[str]) -> int:
    if not args or args[0] not in {"inventory", "show", "decide"}:
        return fail("LEARNING_USAGE", "learning requires inventory, show, or decide", EXIT_USAGE)
    if args[0] == "decide" and "--human-decision" not in args:
        return fail("HUMAN_DECISION_REQUIRED", "learning decide requires --human-decision; moving on leaves the request pending", EXIT_USAGE)
    script = Path(__file__).resolve().parent / "agents" / "skills" / "memory-request-review" / "scripts" / "review_memory_requests.py"
    if not script.is_file():
        return fail("MEMORY_REVIEW_UNAVAILABLE", "native memory-review script is not installed")
    try:
        result = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return fail("MEMORY_REVIEW_UNAVAILABLE", str(exc))
    if result.returncode:
        return fail("MEMORY_REVIEW_FAILED", (result.stderr or result.stdout).strip() or "native memory review failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"display": result.stdout.rstrip()}
    emit({"status": "ok", "command": "learning", "action": args[0], "result": payload})
    return 0


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
    if not args:
        print(usage())
        return 0
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
    if args and args[0] in {"add-source-clone", "set-role", "retry", "evidence", "learning"}:
        try:
            workspace = workspace_path()
        except ValueError as exc:
            return fail("WORKSPACE_NOT_BOUND", str(exc))
        if args[0] == "add-source-clone":
            if len(args) != 3:
                return fail("SOURCE_CLONE_USAGE", "add-source-clone requires PROJECT CLONE", EXIT_USAGE)
            return add_source_clone(args[1], args[2], workspace)
        if args[0] == "set-role":
            if len(args) < 3:
                return fail("ROLE_USAGE", "set-role requires PROJECT ROLE [OPTIONS]", EXIT_USAGE)
            return set_role(args[1], args[2], args[3:], workspace)
        if args[0] == "retry":
            return retry_task(args[1:], workspace)
        if args[0] == "evidence":
            return show_evidence(args[1:], workspace)
        return learning(args[1:])
    return fail("UNKNOWN_COMMAND", f"unknown command: {args[0]}", EXIT_USAGE)


if __name__ == "__main__":
    raise SystemExit(main())
