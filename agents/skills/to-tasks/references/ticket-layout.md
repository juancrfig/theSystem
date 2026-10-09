# Workspace ticket layout

Work records live under `<project>/tickets/`, one folder per ticket.

```text
<project>/tickets/<ticket>/
  ticket.md                          the official ticket: tracker link, id, title; or a local slug
  spec.md                            to-spec: the plan for the whole ticket
  tasks/<task-id>/
    task.md                          YAML front matter plus task instructions and acceptance criteria
    runs/<run-id>/                   written by the main agent (run-tasks), one folder per run
      run.json                       status, timings, branch, worktree, base and worker commits, verdict, error
      worker.diff                    the worker's change
      worker.md                      the worker's final summary
      review.md                      the reviewer's findings and verdict
```

Task ids (the `<task-id>` folder names) are unique across the workspace. Only the main agent writes `runs/` and
changes a task's `status`.
