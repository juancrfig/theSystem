"""One run of one task: the worker writes the change in a git worktree, then a reviewer checks it.

Everything the main agent may need to diagnose a run is kept in
`<task>/runs/<run-id>/`: run.json, review.md, worker.diff, the agents'
transcripts and prompts, the rules and skills each one had, and orchestrator.log.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from thesystem import roles
from thesystem.errors import CodedError
from thesystem.tasks import Task

# Hermes treats an empty -t as "all toolsets"; an unknown name selects none, so a role without tools gets no tools.
NO_TOOLS = "none"
AGENT_TIMEOUT = int(os.environ.get("THESYSTEM_AGENT_TIMEOUT", "3600"))
VERDICT = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\b", re.I | re.M)
COMMITTER = ["-c", "user.name=theSystem", "-c", "user.email=thesystem@localhost"]


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise CodedError("GIT_FAILED", f"git {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def branch_name(task: Task) -> str:
    return f"thesystem/{task.id}"


def worktree_path(workspace: Path, task: Task) -> Path:
    return workspace / ".thesystem" / "worktrees" / task.id


def discard_worktree(workspace: Path, task: Task) -> None:
    clone = task.source_clone
    if not (clone / ".git").exists():
        return
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path(workspace, task))],
                   cwd=clone, capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=clone, capture_output=True)
    subprocess.run(["git", "branch", "-D", branch_name(task)], cwd=clone, capture_output=True)


class Run:
    def __init__(self, workspace: Path, task: Task):
        self.workspace = workspace
        self.task = task
        self.id = time.strftime("%Y%m%d-%H%M%S")
        self.directory = task.directory / "runs" / self.id
        suffix = 1
        while self.directory.exists():
            suffix += 1
            self.directory = task.directory / "runs" / f"{self.id}-{suffix}"
        self.id = self.directory.name
        self.directory.mkdir(parents=True)
        self.record = {"run": self.id, "task": task.id, "started_at": _now()}

    def log(self, message: str) -> None:
        with open(self.directory / "orchestrator.log", "a", encoding="utf-8") as log:
            log.write(f"{_now()} {message}\n")

    def save(self, **fields) -> None:
        self.record.update(fields)
        (self.directory / "run.json").write_text(json.dumps(self.record, indent=2) + "\n", encoding="utf-8")

    def execute(self) -> str:
        """Run the task and return its new status."""
        try:
            status = self._execute()
        except CodedError as error:
            self.log(f"error {error.code}: {error.message}")
            self.save(error={"code": error.code, "message": error.message})
            status = "failed"
        except Exception as error:  # an orchestrator bug must still end the run as failed, with evidence
            self.log(f"error {type(error).__name__}: {error}")
            self.save(error={"code": type(error).__name__, "message": str(error)})
            status = "failed"
        self.save(status=status, finished_at=_now())
        self.log(f"finished: {status}")
        return status

    def _execute(self) -> str:
        task, clone = self.task, self.task.source_clone
        if not (clone / ".git").exists():
            raise CodedError("SOURCE_CLONE_INVALID", f"{clone} is not a git clone")
        worker_context = roles.resolve(self.workspace, task.project, task.roles)
        reviewer_context = roles.resolve(self.workspace, task.project, ["reviewer"])
        reviewer_context.add(roles.Context(rules=worker_context.rules))

        discard_worktree(self.workspace, task)
        base_branch = _current_branch(clone)
        base = git(clone, "rev-parse", "HEAD")
        clone_status = git(clone, "status", "--porcelain")
        work = worktree_path(self.workspace, task)
        work.parent.mkdir(parents=True, exist_ok=True)
        git(clone, "worktree", "add", "-b", branch_name(task), str(work), base)
        self.save(status="running", source_clone=str(clone), base_branch=base_branch, base_commit=base,
                  branch=branch_name(task), worktree=str(work),
                  roles={"worker": task.roles, "reviewer": ["reviewer"]},
                  toolsets={"worker": worker_context.toolsets, "reviewer": reviewer_context.toolsets})
        self.log(f"worker starting in {work}")

        worker = self._agent("worker", work, self._worker_prompt(worker_context), worker_context.toolsets)
        if worker["error"]:
            raise CodedError("WORKER_FAILED", worker["error"])
        self._check_isolation(work, base, base_branch, clone_status)
        git(work, "add", "-A")
        if git(work, "status", "--porcelain"):
            git(work, *COMMITTER, "commit", "-q", "-m", f"{task.id}: worker run {self.id}")
        commit = git(work, "rev-parse", "HEAD")
        if commit == base:
            raise CodedError("WORKER_NO_CHANGES", "the worker finished without changing any file")
        diff = git(work, "diff", base, commit)
        (self.directory / "worker.diff").write_text(diff + "\n", encoding="utf-8")
        self.save(worker_commit=commit)

        self.log("reviewer starting")
        review_dir = self.workspace / ".thesystem" / "reviews" / self.id
        git(clone, "worktree", "add", "--detach", str(review_dir), commit)
        try:
            reviewer = self._agent("reviewer", review_dir, self._reviewer_prompt(reviewer_context, base),
                                   reviewer_context.toolsets)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(review_dir)], cwd=clone, capture_output=True)
        findings = reviewer["text"].strip()
        (self.directory / "review.md").write_text(findings + "\n", encoding="utf-8")
        if reviewer["error"]:
            raise CodedError("REVIEWER_FAILED", reviewer["error"])
        verdicts = VERDICT.findall(findings)
        if not verdicts:
            raise CodedError("REVIEWER_NO_VERDICT", "the reviewer did not end with VERDICT: PASS or VERDICT: FAIL")
        self.save(verdict=verdicts[-1].upper())
        return "pre-done" if verdicts[-1].upper() == "PASS" else "changes-requested"

    def _check_isolation(self, work: Path, base: str, base_branch: str, clone_status: str) -> None:
        """Fail the run when the worker left its worktree: switched branch, committed, or touched the source clone.

        The clone may only have gained merges made by `merge` for other tasks while this one ran.
        """
        problems = []
        if _current_branch(work, missing="detached HEAD") != branch_name(self.task):
            problems.append(f"the worktree is no longer on {branch_name(self.task)}")
        if git(work, "rev-parse", "HEAD") != base:
            problems.append("the worker moved the worktree's HEAD (commit, reset or checkout)")
        clone = self.task.source_clone
        if _current_branch(clone, missing="detached HEAD") != base_branch:
            problems.append(f"the source clone is no longer on {base_branch}")
        foreign = [line for line in git(clone, "log", "--first-parent", "--format=%cn %s", f"{base}..HEAD").splitlines()
                   if not re.fullmatch(r"theSystem Merge task \S+", line)]
        if foreign:
            problems.append(f"the source clone gained commits that are not task merges: {foreign}")
        if git(clone, "status", "--porcelain") != clone_status:
            problems.append("files changed in the source clone")
        if problems:
            raise CodedError("ISOLATION_BROKEN", "; ".join(problems))

    def _worker_prompt(self, context: roles.Context) -> str:
        return "\n".join([
            f"You are the worker for task {self.task.id}.",
            "Your current directory is a git worktree of the source clone. Change files only inside it.",
            "Do not commit, push, merge or switch branches: theSystem commits your changes when you finish.",
            "",
            "# Task",
            "",
            self.task.body.strip(),
            "",
            roles.materialize(context, self.directory / "worker-context"),
        ])

    def _reviewer_prompt(self, context: roles.Context, base: str) -> str:
        return "\n".join([
            f"You are the independent reviewer for task {self.task.id}.",
            "Your current directory is a disposable checkout of the worker's result.",
            f"The worker's change is `git diff {base} HEAD`. Run tests or builds if they help you judge it.",
            "Check the change against the task and its acceptance criteria, and against the rules below.",
            "Report concrete findings. End your answer with exactly one line: VERDICT: PASS or VERDICT: FAIL.",
            "",
            "# Task",
            "",
            self.task.body.strip(),
            "",
            roles.materialize(context, self.directory / "reviewer-context"),
        ])

    def _agent(self, name: str, cwd: Path, prompt: str, toolsets: list[str]) -> dict:
        prompt_file = self.directory / f"{name}-prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        transcript = self.directory / f"{name}.jsonl"
        command = ["hermes", "-p", name, "chat", "--query-file", str(prompt_file), "--in", str(cwd),
                   "--format", "stream-json", "--yolo", "--source", "tool", "-t", ",".join(toolsets) or NO_TOOLS]
        environment = {k: v for k, v in os.environ.items() if k != "TERMINAL_CWD"}
        environment["HERMES_WRITE_SAFE_ROOT"] = str(cwd)  # Hermes' file tools cannot write outside the checkout
        try:
            with open(transcript, "w", encoding="utf-8") as out, open(self.directory / "orchestrator.log", "a") as err:
                process = subprocess.run(command, cwd=cwd, stdout=out, stderr=err, timeout=AGENT_TIMEOUT,
                                         env=environment)
        except FileNotFoundError:
            return {"text": "", "error": "the hermes command is not installed or not on PATH"}
        except subprocess.TimeoutExpired:
            return {"text": _final_text(transcript), "error": f"{name} timed out after {AGENT_TIMEOUT}s"}
        text = _final_text(transcript)
        error = f"{name} exited with code {process.returncode}" if process.returncode else ""
        return {"text": text, "error": error}


def _current_branch(checkout: Path, missing: str = "") -> str:
    result = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=checkout, capture_output=True, text=True)
    branch = result.stdout.strip()
    if branch:
        return branch
    if missing:
        return missing
    raise CodedError("SOURCE_CLONE_DETACHED", f"{checkout} has no branch checked out; tasks merge into a branch")


def _final_text(transcript: Path) -> str:
    text = ""
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            text = event.get("text") or text
    return text


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
