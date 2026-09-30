"""Headless bridge to the native Hermes memory-review workflow."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from thesystem.errors import CodedError


class LearningError(CodedError):
    pass


def review_memory(args: list[str], distribution_root: Path, python: str | None = None) -> dict:
    if not args or args[0] not in {"inventory", "show", "decide"}:
        raise LearningError("LEARNING_USAGE", "learning requires inventory, show, or decide")
    if args[0] == "decide" and "--human-decision" not in args:
        raise LearningError("HUMAN_DECISION_REQUIRED", "learning decide requires --human-decision; moving on leaves the request pending")
    script = Path(distribution_root) / "agents" / "skills" / "memory-request-review" / "scripts" / "review_memory_requests.py"
    if not script.is_file():
        raise LearningError("MEMORY_REVIEW_UNAVAILABLE", "native memory-review script is not installed")
    try:
        result = subprocess.run([python or sys.executable, str(script), *args], text=True,
                                capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LearningError("MEMORY_REVIEW_UNAVAILABLE", str(error)) from error
    if result.returncode:
        raise LearningError("MEMORY_REVIEW_FAILED", (result.stderr or result.stdout).strip() or "native memory review failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"display": result.stdout.rstrip()}
