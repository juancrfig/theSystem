"""One run of one task: the worker writes the change in a git worktree, then a reviewer checks it.

Everything the main agent may need to diagnose a run is kept in
`<task>/runs/<run-id>/`: run.json, review.md, worker.diff, the agents'
transcripts and prompts, the rules and skills each one had, and orchestrator.log.
"""
from __future__ import annotations

import json
import math
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from thesystem import roles
from thesystem.errors import CodedError
from thesystem.tasks import Task, find_all

# Hermes treats an empty -t as "all toolsets"; an unknown name selects none, so a role without tools gets no tools.
NO_TOOLS = "none"
AGENT_TIMEOUT = int(os.environ.get("THESYSTEM_AGENT_TIMEOUT", "3600"))
BOOTSTRAP_DIRECTORY = "agents/bootstrap"
VERDICT = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\b", re.I | re.M)
COMMITTER = ["-c", "user.name=theSystem", "-c", "user.email=thesystem@localhost"]


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise CodedError("GIT_FAILED", f"git {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def branch_name(task: Task) -> str:
    return task.fields["branch"] if "branch" in task.fields else f"thesystem/{task.id}"


def commit_message(task: Task, run_id: str) -> str:
    return task.fields["commit_message"] if "commit_message" in task.fields else f"{task.id}: worker run {run_id}"


def validate_task_configuration(workspace: Path, task: Task) -> None:
    branch = branch_name(task)
    if not isinstance(branch, str) or not branch:
        raise CodedError("TASK_CONFIGURATION_INVALID", "branch must be a non-empty git branch name")
    checked = subprocess.run(["git", "check-ref-format", "--branch", branch], capture_output=True, text=True)
    if checked.returncode:
        raise CodedError("TASK_CONFIGURATION_INVALID", f"invalid branch name {branch!r}")

    message = commit_message(task, "")
    if not isinstance(message, str) or not message.strip() or "\0" in message:
        raise CodedError("TASK_CONFIGURATION_INVALID", "commit_message must be a non-empty string without NUL")

    clone = task.source_clone.resolve()
    for other in find_all(workspace):
        if other.path == task.path:
            continue
        try:
            other_clone = other.source_clone.resolve()
        except (CodedError, TypeError):
            continue
        if other_clone != clone:
            continue
        other_branch = branch_name(other)
        if other_branch == branch:
            raise CodedError("TASK_CONFIGURATION_INVALID",
                             f"branch {branch!r} is also configured for task {other.id!r} in {clone}")

    if (clone / ".git").exists():
        exists = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=clone)
        if exists.returncode == 0 and not _branch_has_run_record(task, branch):
            raise CodedError("TASK_CONFIGURATION_INVALID", f"branch {branch!r} already exists in {clone}")


def _branch_has_run_record(task: Task, branch: str) -> bool:
    for path in sorted((task.directory / "runs").glob("*/run.json")):
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("branch") == branch:
                return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


def worktree_path(workspace: Path, task: Task) -> Path:
    return workspace / ".thesystem" / "worktrees" / task.id


def discard_worktree(workspace: Path, task: Task, delete_branch: bool = True) -> None:
    clone = task.source_clone
    if not (clone / ".git").exists():
        return
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path(workspace, task))],
                   cwd=clone, capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=clone, capture_output=True)
    if delete_branch:
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
        validate_task_configuration(self.workspace, task)
        worker_context = roles.resolve(self.workspace, task.project, task.roles)
        reviewer_context = roles.resolve(self.workspace, task.project, ["reviewer"])
        reviewer_context.add(roles.Context(rules=worker_context.rules))

        discard_worktree(self.workspace, task, delete_branch=False)
        base_branch = _current_branch(clone)
        base = git(clone, "rev-parse", "HEAD")
        clone_status = git(clone, "status", "--porcelain")
        work = worktree_path(self.workspace, task)
        work.parent.mkdir(parents=True, exist_ok=True)
        existing_branch = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name(task)}"],
                                        cwd=clone).returncode == 0
        if existing_branch:
            git(clone, "worktree", "add", str(work), branch_name(task))
            branch_head = git(work, "rev-parse", "HEAD")
        else:
            git(clone, "worktree", "add", "-b", branch_name(task), str(work), base)
            branch_head = base
        self.save(status="running", source_clone=str(clone), base_branch=base_branch, base_commit=base,
                  branch=branch_name(task), commit_message=commit_message(task, self.id), worktree=str(work),
                  roles={"worker": task.roles, "reviewer": ["reviewer"]},
                  toolsets={"worker": worker_context.toolsets, "reviewer": reviewer_context.toolsets})
        self.log(f"worker starting in {work}")

        bootstrap = self._snapshot_bootstrap()
        self._bootstrap("worker", work, bootstrap, branch_head, branch_name(task))
        worker = self._agent("worker", work, self._worker_prompt(worker_context), worker_context.toolsets)
        if worker["error"]:
            raise CodedError("WORKER_FAILED", worker["error"])
        self._check_isolation(work, branch_head, base, base_branch, clone_status)
        git(work, "add", "-A")
        if git(work, "status", "--porcelain"):
            git(work, *COMMITTER, "commit", "-q", "-m", commit_message(task, self.id))
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
            self._bootstrap("reviewer", review_dir, bootstrap, commit, "detached HEAD")
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

    def _snapshot_bootstrap(self) -> dict | None:
        """Capture project-level bootstrap bytes once, before either agent can run."""
        source_clone = self.task.fields.get("source_clone")
        if (not isinstance(source_clone, str) or not source_clone or source_clone in (".", "..")
                or Path(source_clone).name != source_clone or "/" in source_clone or "\\" in source_clone
                or "\0" in source_clone):
            raise CodedError("BOOTSTRAP_CONFIGURATION_INVALID",
                             "source_clone must be a single relative folder name for bootstrap lookup")

        project = self.task.project.resolve()
        bootstrap_root = (self.task.project / BOOTSTRAP_DIRECTORY).resolve()
        if not bootstrap_root.is_relative_to(project):
            raise CodedError("BOOTSTRAP_CONFIGURATION_INVALID", "project bootstrap directory escapes the project")
        source = bootstrap_root / source_clone
        resolved_source = source.resolve()
        if not resolved_source.is_relative_to(bootstrap_root):
            raise CodedError("BOOTSTRAP_CONFIGURATION_INVALID", "project bootstrap path escapes its directory")
        if not source.exists() and not source.is_symlink():
            self.save(bootstrap_snapshot={"status": "absent"})
            return None
        try:
            metadata = resolved_source.stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise CodedError("BOOTSTRAP_CONFIGURATION_INVALID", "project bootstrap must be a regular file")
            content = resolved_source.read_bytes()
            snapshot_path = self.directory / "bootstrap.snapshot"
            snapshot_path.write_bytes(content)
            snapshot_path.chmod(0o600)
        except OSError as error:
            raise CodedError("BOOTSTRAP_FAILED", f"project bootstrap could not be snapshotted ({type(error).__name__})")

        snapshot = {
            "content": content,
            "executable": bool(metadata.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)),
        }
        self.save(bootstrap_snapshot={"status": "present", "source": f"{BOOTSTRAP_DIRECTORY}/{source_clone}",
                                      "evidence": snapshot_path.name})
        return snapshot

    def _bootstrap(self, role: str, cwd: Path, snapshot: dict | None,
                   expected_head: str, expected_branch: str) -> None:
        """Run the immutable project bootstrap snapshot in the agent's worktree."""
        if snapshot is None:
            self._record_bootstrap(role, {"status": "absent"})
            self.log(f"{role} bootstrap absent")
            return

        if not snapshot["executable"]:
            self._record_bootstrap(role, {"status": "failed", "reason": "not_executable"})
            raise CodedError("BOOTSTRAP_FAILED", f"{role} project bootstrap must be executable")
        content = snapshot["content"]
        try:
            timeout = float(os.environ.get("THESYSTEM_BOOTSTRAP_TIMEOUT", "300"))
        except ValueError:
            self._record_bootstrap(role, {"status": "failed", "reason": "invalid_timeout"})
            raise CodedError("BOOTSTRAP_CONFIGURATION_INVALID", "THESYSTEM_BOOTSTRAP_TIMEOUT must be finite and positive")
        if not math.isfinite(timeout) or timeout <= 0:
            self._record_bootstrap(role, {"status": "failed", "reason": "invalid_timeout"})
            raise CodedError("BOOTSTRAP_CONFIGURATION_INVALID", "THESYSTEM_BOOTSTRAP_TIMEOUT must be finite and positive")

        script_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix=f"{role}-bootstrap-", delete=False) as script:
                script.write(content)
                script_path = Path(script.name)
            script_path.chmod(0o700)
        except OSError as error:
            if script_path is not None:
                script_path.unlink(missing_ok=True)
            self._record_bootstrap(role, {"status": "failed", "reason": "prepare_failed"})
            raise CodedError("BOOTSTRAP_FAILED", f"{role} bootstrap could not be prepared ({type(error).__name__})")

        try:
            environment = os.environ.copy()
            environment["THESYSTEM_BOOTSTRAP_ROLE"] = role
            self._record_bootstrap(role, {"status": "running"})
            try:
                process = subprocess.Popen([str(script_path)], cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           start_new_session=True)
            except OSError as error:
                self._record_bootstrap(role, {"status": "failed", "reason": "start_failed"})
                raise CodedError("BOOTSTRAP_FAILED", f"{role} bootstrap could not start ({type(error).__name__})")
            try:
                process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
                self._record_bootstrap(role, {"status": "timed_out", "timeout_seconds": timeout})
                self.log(f"{role} bootstrap timed out after {timeout:g}s")
                raise CodedError("BOOTSTRAP_TIMEOUT", f"{role} bootstrap timed out after {timeout:g}s")

            if process.returncode:
                self._record_bootstrap(role, {"status": "failed", "exit_code": process.returncode})
                self.log(f"{role} bootstrap failed with exit code {process.returncode}")
                raise CodedError("BOOTSTRAP_FAILED", f"{role} bootstrap exited with code {process.returncode}")

            current_head = git(cwd, "rev-parse", "HEAD")
            current_branch = _current_branch(cwd, missing="detached HEAD")
            if current_head != expected_head or current_branch != expected_branch:
                self._record_bootstrap(role, {"status": "failed", "reason": "checkout_modified"})
                self.log(f"{role} bootstrap changed the worktree checkout")
                raise CodedError("BOOTSTRAP_FAILED", f"{role} bootstrap changed the worktree checkout")
            tracked_changes = subprocess.run(["git", "diff", "--quiet", expected_head, "--"], cwd=cwd).returncode
            if tracked_changes:
                self._record_bootstrap(role, {"status": "failed", "reason": "tracked_files_modified"})
                self.log(f"{role} bootstrap modified tracked files")
                raise CodedError("BOOTSTRAP_FAILED", f"{role} bootstrap modified tracked files")
            self._record_bootstrap(role, {"status": "succeeded", "exit_code": 0})
            self.log(f"{role} bootstrap succeeded (exit code 0)")
        finally:
            if script_path is not None:
                script_path.unlink(missing_ok=True)

    def _record_bootstrap(self, role: str, result: dict) -> None:
        bootstrap = self.record.get("bootstrap")
        if not isinstance(bootstrap, dict):
            bootstrap = {}
        bootstrap[role] = result
        self.save(bootstrap=bootstrap)

    def _check_isolation(self, work: Path, branch_head: str, base: str, base_branch: str, clone_status: str) -> None:
        """Fail the run when the worker left its worktree: switched branch, committed, or touched the source clone.

        The clone may only have gained merges made by `merge` for other tasks while this one ran.
        """
        problems = []
        if _current_branch(work, missing="detached HEAD") != branch_name(self.task):
            problems.append(f"the worktree is no longer on {branch_name(self.task)}")
        if git(work, "rev-parse", "HEAD") != branch_head:
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
