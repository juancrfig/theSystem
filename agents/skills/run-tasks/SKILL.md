---
name: run-tasks
description: Use when approved theSystem tasks must run, be retried or merged. The main agent delegates each task to a worker subagent and then a reviewer subagent.
---

# Run Tasks

You, the main agent, are the orchestrator. There is no orchestrator program: you read the task files, delegate each
task to subagents, record the run and update the task's `status`. Every task `to-tasks` writes is approved, so run
ready tasks without asking again.

Read [Workspace ticket layout](../to-tasks/references/ticket-layout.md) first. Follow
`../../rules/tests-and-verification-need-human-approval.md`: workers and reviewers write no tests and verify nothing
unless the task quotes the human's explicit approval.

## 1. Find the ready tasks

1. Read the front matter of every `*/tickets/*/tasks/*/task.md` in the workspace. A missing `status` means `ready`.
2. A `blocked` task becomes `ready` when every `task:` blocker is `done` and it has no `external:` blocker. A `ready`
   task with an open blocker becomes `blocked`. Write each change back to the task's front matter.
3. A task left `running` with no live subagent (for example after a restart) becomes `failed`; record why in its
   last `run.json`.

Run all ready tasks in parallel, up to 3 at a time: one `delegate_task` call with one entry per task. When a task
becomes `done`, repeat this step: its dependents may now be ready.

## 2. Prepare the run

For each task, in its project's source clone (`<project>/<source_clone>`):

1. The clone must be a git repo with a branch checked out. Note that branch (the base branch) and its `HEAD` (the
   base commit).
2. Branch: the task's `branch` field, or `thesystem/<task-id>`. Reuse it if it exists (a retry keeps earlier commits).
3. Create the worktree at `<workspace>/.thesystem/worktrees/<task-id>`:
   `git worktree add -b <branch> <path> <base>` (or `git worktree add <path> <branch>` when the branch exists).
4. Create `<task>/runs/<run-id>/` with `run-id` = `YYYYMMDD-HHMMSS`. Write `run.json` with `status: running`, the
   start time, the base branch, base commit, branch and worktree. Set the task's `status: running`.
5. Resolve the roles: merge `agents/roles.yaml` with `<project>/agents/roles.yaml` (a project role replaces a global
   role with the same name). The worker gets `base` then the task's `roles`. The reviewer gets `base`, `reviewer` and
   the worker's rules. Collect the absolute paths of each agent's rule files and skill folders.

## 3. Delegate the worker

One `delegate_task` entry per task. Subagents know nothing of this conversation, so the `context` holds everything:

- "You are the worker for task `<task-id>`. Work only inside `<worktree path>`; cd there first. Do not commit, push,
  merge or switch branches: the main agent commits your change."
- The full task body (below the front matter), verbatim.
- The worker's rules: paste each rule file in full.
- The worker's skills: list each `SKILL.md` path and tell it to read the ones that apply before working.
- "Do not write, change or run tests, and do not run the application, builds, linters or checks to verify your work,
  unless the task quotes the human's approval. If the task leaves a decision open that you need, stop and say so
  instead of guessing."
- "End with a short summary: what you changed and anything left undone."

When the worker returns:

1. Save its summary as `worker.md`.
2. Check isolation: the worktree is still on its branch with `HEAD` unchanged, and the source clone is on its base
   branch with no new uncommitted changes. If not, the run is `failed`.
3. `git add -A` and commit in the worktree with the task's `commit_message` field, or `<task-id>: worker run
   <run-id>`. Use `-c user.name=theSystem -c user.email=thesystem@localhost`.
4. No change at all: the run is `failed` ("the worker finished without changing any file").
5. Save `git diff <base> <commit>` as `worker.diff`, and record the commit in `run.json`.

## 4. Delegate the reviewer

One `delegate_task` entry per task, after its worker. The `context` holds:

- "You are the independent reviewer for task `<task-id>`. Read the worker's change with
  `git -C <worktree> diff <base> <commit>`. Do not change any file."
- The full task body, the reviewer's rules (pasted in full) and its skill paths (`code-review` at least).
- "Review only by reading the diff and the code. Do not run tests, the application, builds or checks unless the task
  quotes the human's approval. Check the change against the task and its acceptance criteria, and against the rules."
- "Report concrete findings. End with exactly one line: `VERDICT: PASS` or `VERDICT: FAIL`."

Save the answer as `review.md` and the verdict in `run.json`. No verdict line: the run is `failed`.

## 5. Decide

- `PASS`: the task becomes `pre-done`. Tell the human it waits for their merge.
- `FAIL` on the first run: retry once on your own. Start a new run (step 2 reuses the branch) and add the reviewer's
  findings to the worker's context under "Fix these review findings".
- `FAIL` on the retry: the task becomes `changes-requested`. Bring it to the human.
- A broken run (delegation error, isolation broken, no change, no verdict): the task becomes `failed`. Record
  `{"code", "message"}` under `error` in `run.json` and bring it to the human.

Finish each run: set `status` and `finished_at` in `run.json`. Report outcomes only: which tasks are `pre-done`, and
which need the human, with the reason.

## Merge (the human said merge)

Only a `pre-done` task merges.

1. In the source clone, check that the current branch is the run's base branch. If not, stop and tell the human.
2. `git -c user.name=theSystem -c user.email=thesystem@localhost merge --no-ff -m "Merge task <task-id>" <branch>`.
   On a conflict, `git merge --abort` and bring it to the human.
3. Remove the worktree (`git worktree remove --force <path>`, then `git worktree prune`) and delete the branch.
4. Set the task's `status: done`, then go back to step 1: blocked tasks may now be ready.
5. When every task of the ticket is `done`, propose candidate tests to the human (see the workspace guide). Create a
   test task only for the tests the human approves, quoting that approval in the task body.

## Retry (after the human improved the roles)

Only a `changes-requested`, `failed` or `pre-done` task retries. Remove its worktree but keep its branch, set
`status: ready`, and run it from step 2. The retry counter starts again: one automatic retry after a `FAIL`.
