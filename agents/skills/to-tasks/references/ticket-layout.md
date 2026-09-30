# Workspace ticket layout

For company/product projects using the workspace ticket tree, work records live under `<project>/tickets/`, keyed by ticket. Global workspace work and development of theSystem use GitHub exclusively, as defined in the root `AGENTS.md`; never create root `tickets/` or local planning/ticket artifacts for that scope. The layout below applies only to company/product execution records, not the global workspace's development tracker.

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
