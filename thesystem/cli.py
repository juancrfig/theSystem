"""The workspace command (named after the company at install time). Used by agents; output is JSON."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from thesystem import runner, tasks
from thesystem.errors import CodedError

MAX_PARALLEL = int(os.environ.get("THESYSTEM_MAX_PARALLEL", "2"))
HELP = """\
usage: {prog} <command>

  run           start every ready task (to-tasks calls this when it finishes)
  merge <task>  merge a pre-done task into its source clone; the task becomes done
  retry <task>  send a changes-requested, failed or pre-done task back to run again

Task state lives in each task.md; run evidence in <task>/runs/<run-id>/.
"""


def state_dir(workspace: Path) -> Path:
    path = workspace / ".thesystem"
    path.mkdir(exist_ok=True)
    return path


def dispatcher_lock(workspace: Path):
    """Held for the dispatcher's whole life, so only one dispatcher runs per workspace."""
    handle = open(state_dir(workspace) / "dispatcher.lock", "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def summary(workspace: Path) -> dict:
    counts: dict[str, list[str]] = {}
    for task in tasks.find_all(workspace):
        counts.setdefault(task.status, []).append(task.id)
    return counts


def command_run(workspace: Path) -> dict:
    lock = dispatcher_lock(workspace)
    if lock is None:
        return {"status": "ok", "dispatcher": "already running", "tasks": summary(workspace)}
    try:
        for task in tasks.find_all(workspace):
            if task.status == "running":  # no dispatcher holds the lock, so this run died with it
                task.set_status("failed")
                _record_abandoned(task)
        tasks.refresh_waiting(tasks.find_all(workspace))
    finally:
        lock.close()
    log = open(state_dir(workspace) / "dispatcher.log", "a")
    package_root = str(Path(__file__).resolve().parents[1])
    environment = {**os.environ, "PYTHONPATH": package_root}
    subprocess.Popen([sys.executable, "-m", "thesystem.cli", "--workspace", str(workspace), "_dispatch"],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
                     env=environment, cwd=package_root)
    return {"status": "ok", "dispatcher": "started", "tasks": summary(workspace)}


def _record_abandoned(task: tasks.Task) -> None:
    runs = sorted((task.directory / "runs").glob("*/run.json"))
    if runs:
        record = json.loads(runs[-1].read_text(encoding="utf-8"))
        if record.get("status") == "running":
            record.update(status="failed", error={"code": "ORCHESTRATOR_STOPPED",
                                                  "message": "the orchestrator stopped while this run was in progress"})
            runs[-1].write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def dispatch(workspace: Path) -> None:
    lock = dispatcher_lock(workspace)
    if lock is None:
        return
    active: dict[str, threading.Thread] = {}
    while True:
        active = {task_id: thread for task_id, thread in active.items() if thread.is_alive()}
        all_tasks = tasks.find_all(workspace)
        tasks.refresh_waiting(all_tasks)
        ready = [task for task in all_tasks if task.status == "ready" and task.id not in active]
        for task in ready[: max(0, MAX_PARALLEL - len(active))]:
            task.set_status("running")
            thread = threading.Thread(target=_run_task, args=(workspace, task), daemon=False)
            thread.start()
            active[task.id] = thread
        if not active:
            break
        time.sleep(2)
    lock.close()


def _run_task(workspace: Path, task: tasks.Task) -> None:
    status = runner.Run(workspace, task).execute()
    task.set_status(status)


def command_merge(workspace: Path, task_id: str) -> dict:
    task = tasks.find(workspace, task_id)
    if task.status != "pre-done":
        raise CodedError("NOT_PRE_DONE", f"task {task_id} is {task.status}; only pre-done tasks can be merged")
    clone, branch = task.source_clone, runner.branch_name(task)
    merged = subprocess.run(["git", *runner.COMMITTER, "merge", "--no-ff", "-m", f"Merge task {task_id}", branch],
                            cwd=clone, capture_output=True, text=True)
    if merged.returncode:
        subprocess.run(["git", "merge", "--abort"], cwd=clone, capture_output=True)
        raise CodedError("MERGE_FAILED", (merged.stderr or merged.stdout).strip())
    commit = runner.git(clone, "rev-parse", "HEAD")
    runner.discard_worktree(workspace, task)
    task.set_status("done")
    started = command_run(workspace)
    return {"status": "ok", "task": task_id, "merge_commit": commit, "dispatcher": started["dispatcher"]}


def command_retry(workspace: Path, task_id: str) -> dict:
    task = tasks.find(workspace, task_id)
    if task.status not in tasks.RETRYABLE:
        raise CodedError("NOT_RETRYABLE", f"task {task_id} is {task.status}; retry needs one of {', '.join(tasks.RETRYABLE)}")
    runner.discard_worktree(workspace, task)
    task.set_status("ready")
    started = command_run(workspace)
    return {"status": "ok", "task": task_id, "dispatcher": started["dispatcher"]}


def main(argv: list[str] | None = None) -> int:
    prog = os.environ.get("THESYSTEM_COMMAND", "thesystem")
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--workspace", default=os.environ.get("THESYSTEM_WORKSPACE"))
    parser.add_argument("command", nargs="?")
    parser.add_argument("task", nargs="?")
    args, extra = parser.parse_known_args(argv)
    if args.command in (None, "-h", "--help", "help"):
        print(HELP.format(prog=prog), end="")
        return 0
    try:
        if extra or not args.workspace:
            raise CodedError("USAGE", "unexpected arguments" if extra else "no workspace configured")
        workspace = Path(args.workspace).expanduser().resolve()
        if args.command == "_dispatch":
            dispatch(workspace)
            return 0
        if args.command == "run" and not args.task:
            result = command_run(workspace)
        elif args.command in ("merge", "retry") and args.task:
            result = (command_merge if args.command == "merge" else command_retry)(workspace, args.task)
        else:
            raise CodedError("USAGE", HELP.format(prog=prog).strip())
    except CodedError as error:
        print(json.dumps({"status": "error", "code": error.code, "message": error.message}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
