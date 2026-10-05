"""Tasks are `<project>/tickets/<ticket>/tasks/<task-id>/task.md` files. The file is the only record of a task."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thesystem import frontmatter
from thesystem.errors import CodedError

STATUSES = ("blocked", "ready", "running", "changes-requested", "failed", "pre-done", "done")
WAITING = ("blocked", "ready")
RETRYABLE = ("changes-requested", "failed", "pre-done")


@dataclass
class Task:
    id: str
    path: Path
    fields: dict
    body: str

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def project(self) -> Path:
        return self.path.parents[4]

    @property
    def status(self) -> str:
        return self.fields.get("status") or "ready"

    @property
    def source_clone(self) -> Path:
        name = self.fields.get("source_clone")
        if not name:
            raise CodedError("SOURCE_CLONE_MISSING", f"{self.path}: front matter needs source_clone")
        return self.project / name

    @property
    def roles(self) -> list[str]:
        return _names(self.fields.get("roles")) or ["worker"]

    def set_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        frontmatter.write_field(self.path, "status", status)
        self.fields["status"] = status

    def blocking(self, statuses: dict[str, str]) -> list[str]:
        """Reasons this task cannot start yet; empty when it is ready."""
        reasons = []
        for blocker in self.fields.get("blockers") or []:
            if isinstance(blocker, dict) and "task" in blocker:
                if statuses.get(str(blocker["task"])) != "done":
                    reasons.append(f"task {blocker['task']}")
            elif isinstance(blocker, dict) and "external" in blocker:
                reasons.append(f"external: {blocker['external']}")
            else:
                reasons.append(f"unreadable blocker {blocker!r}")
        return reasons


def _names(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value or []]


def find_all(workspace: Path) -> list[Task]:
    tasks = []
    for path in sorted(workspace.glob("*/tickets/*/tasks/*/task.md")):
        fields, body = frontmatter.read_front_matter(path)
        tasks.append(Task(path.parent.name, path, fields, body))
    seen: dict[str, Path] = {}
    for task in tasks:
        if task.id in seen:
            raise CodedError("DUPLICATE_TASK_ID", f"task id {task.id!r} is used by {seen[task.id]} and {task.path}")
        seen[task.id] = task.path
    return tasks


def find(workspace: Path, task_id: str) -> Task:
    for task in find_all(workspace):
        if task.id == task_id:
            return task
    raise CodedError("TASK_NOT_FOUND", task_id)


def refresh_waiting(tasks: list[Task]) -> None:
    """Move tasks between blocked and ready as their blockers change."""
    statuses = {task.id: task.status for task in tasks}
    for task in tasks:
        if task.status in WAITING:
            wanted = "blocked" if task.blocking(statuses) else "ready"
            if task.status != wanted or "status" not in task.fields:
                task.set_status(wanted)
