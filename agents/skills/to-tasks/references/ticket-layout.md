# Workspace ticket layout

For projects using the workspace ticket tree, work records live under `<project>/tickets/`, keyed by ticket. Workspace-level work, if any, uses root `tickets/` with the same layout.

```text
<project>/tickets/<ticket>/
  ticket.md                          the official ticket: tracker link, id, title; or a local slug
  spec.md                            to-spec: the plan for the whole ticket
  tasks/<task-id>/
    task.md                          YAML front matter plus task instructions and acceptance criteria
    runs/<run-id>/
      run.json                       the run's terminal state
      learnings-review.json          the human's decision on each learning
```

This layout describes durable workspace records, not scratch-ticket drafts or an external tracker's representation. It does not select a tracker or authorize creation, execution, or changes to run records. Follow the project's documented tracker and `MANUAL.md` for workflow, approval, and record ownership.
