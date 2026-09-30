"""Project-scoped retry and immutable evidence operations used by the company CLI."""
from __future__ import annotations

import json
from pathlib import Path
import re

from thesystem.errors import CodedError


class ProjectOperationError(CodedError):
    pass


_RETRYABLE = {
    "changes-requested", "execution-failed", "review-failed", "cancelled", "timeout",
    "aborted", "infra_blocked", "isolation_violated",
}
_RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")


def retry_task(project: str | Path, task_id: str):
    from the_system_orchestrator import Orchestrator

    orchestrator = Orchestrator(project)
    task = orchestrator.task(task_id)
    runs = [run for run in orchestrator.state["runs"].values() if run.get("task_id") == task_id]
    latest = max(runs, key=lambda run: run.get("finished_at", run.get("started_at", ""))) if runs else None
    if not latest or latest.get("status") not in _RETRYABLE:
        raise ProjectOperationError("RETRY_NOT_ALLOWED", "retry requires a prior failed, cancelled, timed-out, or aborted run")
    if task.get("approval") != "approved":
        raise ProjectOperationError("TASK_NOT_APPROVED", "retry requires an approved task")
    return orchestrator.start(task_id, detach=True)


def read_evidence(project: str | Path, run_id: str) -> dict:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ProjectOperationError("EVIDENCE_USAGE", "run identifier is invalid")
    target = Path(project) / ".thesystem" / "orchestrator" / "runs" / f"{run_id}.json"
    try:
        target.lstat()
    except FileNotFoundError as error:
        raise ProjectOperationError("EVIDENCE_NOT_FOUND", "no immutable evidence exists for that run") from error
    if target.is_symlink() or not target.is_file():
        raise ProjectOperationError("EVIDENCE_INVALID", "run evidence is not a regular file")
    try:
        record = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectOperationError("EVIDENCE_INVALID", f"cannot read run evidence: {error}") from error
    if not isinstance(record, dict) or record.get("id") != run_id:
        raise ProjectOperationError("EVIDENCE_INVALID", "run evidence does not match the requested run")
    return record
