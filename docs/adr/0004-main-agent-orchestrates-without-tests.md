# ADR 0004: The main agent orchestrates tasks; no tests or verification without approval

- **Status:** Accepted (branch `no-tests-main-orchestrator` only)
- **Date:** 2026-10-09
- **Supersedes:** ADR 0001 on this branch

## Context

On `master`, a separate orchestrator program runs each approved task with a worker and a reviewer in their own
Hermes profiles, and skills tell agents to write tests and verify their work. The owner wants an alternative where:

- Tests are a scarce good. They are created only at the end of development, and only with explicit human approval.
- Verification follows the same principle: agents do not verify their work unless the human asks.
- The main agent itself orchestrates: after grilling, spec and task split, it delegates each task to subagents.

## Decision

- Remove the orchestrator program (`run`, `merge`, `retry`), the run-awareness integration, the worker and reviewer
  Hermes profiles and theSystem's own test suite. The workspace command keeps only `update`.
- The main agent runs tasks with the `run-tasks` skill: one worker subagent per task in its own git worktree, then a
  reviewer subagent that only reads the diff. Ready tasks run in parallel. A `FAIL` is retried once automatically with
  the review findings; a second `FAIL` goes to the human. Merge still waits for the human.
- Roles keep rules and skills. They lose `tools`, because subagents always inherit the main agent's tools.
- Run evidence is `run.json`, `worker.diff`, `worker.md` and `review.md`. No full transcripts.
- When every task of a ticket is done, the main agent proposes candidate tests; only approved tests become a task.
- This branch is its own release channel: install and `update` follow the newest commit of the branch, not tags.

## Consequences

- No program enforces worktree isolation or tool limits; the main agent checks isolation after each worker.
- Less evidence for diagnosing failed runs.
- `install` and `update` have no automated safety net on this branch.
- `master` is unchanged and remains the tested, script-orchestrated version.
