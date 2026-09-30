#!/usr/bin/env python3
"""Non-chat company command for workspace, task, evidence, and learning operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


# Installed entry points must not leave unowned caches behind after rollback.
if __name__ == "__main__":
    sys.dont_write_bytecode = True

from thesystem.guidance import GuidanceError, update_project_role
from thesystem.learning import LearningError, review_memory
from thesystem.workspace import Workspace, WorkspaceError

# Orchestrator is imported lazily so registration remains usable in a minimal
# installed distribution that predates the optional execution module.

ProjectError = WorkspaceError

EXIT_ERROR = 1
EXIT_USAGE = 2


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


def _parse_options(args: list[str], value_options: set[str], required: set[str], flags=frozenset()):
    values = {}
    seen_flags = set()
    index = 0
    while index < len(args):
        option = args[index]
        if option in flags:
            if option in seen_flags:
                return {}, f"option {option} was specified more than once"
            seen_flags.add(option)
            index += 1
            continue
        if option not in value_options:
            return {}, f"unknown option: {option}"
        if option in values:
            return {}, f"option {option} was specified more than once"
        if index + 1 == len(args) or args[index + 1].startswith("--"):
            return {}, f"option {option} requires a value"
        values[option] = args[index + 1]
        index += 2
    missing = sorted(required - values.keys())
    if missing:
        return {}, f"missing required option: {missing[0]}"
    return values, None


def run_orchestrator(args: list[str]) -> int:
    """Run orchestration operations directly, after validating company scope."""
    if args and args[0] == "orchestrator":
        args = args[1:]
    if not args:
        return fail("UNKNOWN_COMMAND", "orchestrator action is required", EXIT_USAGE)
    action, *raw_options = args
    schemas = {
        "create-task": ({"--project", "--task", "--source-clone", "--command", "--runtime", "--ticket"}, {"--project", "--task", "--source-clone", "--command"}),
        "approve": ({"--project", "--task", "--timeout", "--dispatch"}, {"--project", "--task"}),
        "start": ({"--project", "--task", "--timeout", "--dispatch"}, {"--project", "--task"}),
        "status": ({"--project", "--task"}, {"--project"}),
        "cancel": ({"--project", "--run"}, {"--project", "--run"}),
        "integrate": ({"--project", "--run"}, {"--project", "--run"}),
    }
    if action not in schemas:
        return fail("UNKNOWN_COMMAND", f"unknown orchestrator command: {action}", EXIT_USAGE)
    value_options, required_options = schemas[action]
    options, error = _parse_options(raw_options, value_options, required_options, frozenset({"--dispatch"}))
    if error:
        return fail("ORCHESTRATOR_USAGE", error, EXIT_USAGE)
    try:
        timeout = int(options.get("--timeout", "3600"))
        if not 1 <= timeout <= 3600:
            raise ValueError
    except ValueError:
        return fail("TIMEOUT_INVALID", "attempt timeout must be 1..3600 seconds", EXIT_USAGE)
    try:
        try:
            bound_workspace = workspace_path()
        except ValueError as error:
            return fail("WORKSPACE_NOT_BOUND", str(error))
        workspace = Workspace(bound_workspace)
        project = workspace.require_registered_project(options["--project"])
        clone = workspace.require_registered_clone(project, options["--source-clone"]) if action == "create-task" else None
        from the_system_orchestrator import Orchestrator
        orchestrator = Orchestrator(project)
        if action == "create-task":
            result = orchestrator.create_task(options["--task"], clone, options["--command"],
                                              options.get("--runtime", "hermes"), options.get("--ticket", "local"))
        elif action == "approve":
            result = orchestrator.approve(options["--task"], timeout=timeout)
        elif action == "start":
            result = orchestrator.start(options["--task"], timeout=timeout, detach=True)
        elif action == "status":
            result = orchestrator.status(options.get("--task"))
        elif action == "cancel":
            result = orchestrator.cancel(options["--run"])
        else:
            result = orchestrator.integrate(options["--run"])
    except WorkspaceError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE)
    except Exception as exc:
        code = getattr(exc, "code", "ORCHESTRATOR_UNAVAILABLE")
        return fail(code, str(exc), EXIT_USAGE if code in {"TASK_NOT_FOUND", "TASK_NOT_APPROVED"} else EXIT_ERROR)
    print(json.dumps(result, sort_keys=True))
    return 0


def _lstat(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def add_project(raw: str, workspace: Path) -> int:
    try:
        result = Workspace(workspace).register_project(raw)
    except WorkspaceError as exc:
        return fail(exc.code, str(exc))
    emit({"status": "ok", "command": "add-project", **result})
    return 0


def _registered_project(raw: str, workspace: Path) -> Path:
    return Workspace(workspace).require_registered_project(raw)


def add_source_clone(raw_project: str, raw_clone: str, workspace: Path) -> int:
    try:
        result = Workspace(workspace).register_source_clone(raw_project, raw_clone)
    except WorkspaceError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE if exc.code == "PROJECT_NOT_REGISTERED" else EXIT_ERROR)
    emit({"status": "ok", "command": "add-source-clone", **result})
    return 0


def set_role(raw_project: str, role: str, options: list[str], workspace: Path) -> int:
    flags = {"--rule": "rules", "--skill": "skills", "--tool": "tools", "--util": "utils",
             "--cli": "clis", "--mcp": "mcp_servers"}
    values: dict[str, list[str]] = {}
    index = 0
    while index < len(options):
        flag = options[index]
        if flag not in flags or index + 1 == len(options) or options[index + 1].startswith("--"):
            return fail("ROLE_USAGE", "set-role options are --rule, --skill, --tool, --util, --cli, or --mcp followed by a value", EXIT_USAGE)
        values.setdefault(flags[flag], []).append(options[index + 1])
        index += 2
    try:
        result = update_project_role(Workspace(workspace), raw_project, role, values)
    except (WorkspaceError, GuidanceError) as exc:
        return fail(exc.code, str(exc), EXIT_USAGE if exc.code in {"PROJECT_NOT_REGISTERED", "ROLE_INVALID", "REVIEWER_RULES_MISSING"} else EXIT_ERROR)
    emit({"status": "ok", "command": "set-role", **result})
    return 0


def _option_value(args: list[str], option: str) -> str | None:
    try:
        position = args.index(option)
    except ValueError:
        return None
    return args[position + 1] if position + 1 < len(args) else None


def _replace_option_value(args: list[str], option: str, value: str) -> None:
    args[args.index(option) + 1] = value


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
    try:
        result = review_memory(args, Path(__file__).resolve().parent.parent)
    except LearningError as exc:
        return fail(exc.code, str(exc), EXIT_USAGE if exc.code in {"LEARNING_USAGE", "HUMAN_DECISION_REQUIRED"} else EXIT_ERROR)
    emit({"status": "ok", "command": "learning", "action": args[0], "result": result})
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
