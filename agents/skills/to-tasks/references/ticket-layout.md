# Workspace ticket layout

For company/product projects in a theSystem workspace, work records live under `<project>/tickets/`, keyed by ticket. Development of theSystem itself uses GitHub Issues, as defined in the theSystem repository's `AGENTS.md`.

```text
<project>/tickets/<ticket>/
  ticket.md                          the official ticket: tracker link, id, title; or a local slug
  spec.md                            to-spec: the plan for the whole ticket
  tasks/<task-id>/
    task.md                          YAML front matter plus task instructions and acceptance criteria
    runs/<run-id>/                   written by the orchestrator, one folder per run
      run.json                       status, timings, branch, worktree, error
      review.md                      the reviewer's findings and verdict
      worker.diff                    the worker's change
      worker.jsonl, reviewer.jsonl   full agent transcripts
      worker-prompt.md, reviewer-prompt.md
      worker-context/, reviewer-context/   the exact rules and skills each agent had
      orchestrator.log
```

Task ids (the `<task-id>` folder names) are unique across the workspace. Only the orchestrator writes `runs/` and changes a task's `status` once it is running.
