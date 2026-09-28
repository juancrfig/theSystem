# Workspace guide

This workspace contains one folder per company project. A project can contain multiple source clones.

For the human-owned functional contract, availability labels, workflow, role semantics, and execution guarantees, use [MANUAL.md](MANUAL.md). This file is limited to repository/workspace navigation and the on-disk ticket structure; it is not a second product manual.

# Start here

- [MANUAL.md](MANUAL.md) - intended behavior and practical user guidance. Follow its review status and availability labels; report discrepancies instead of changing the contract to match implementation.
- [CONTEXT.md](CONTEXT.md) - workspace glossary for system terminology.
- `<project>/CONTEXT.md` - project glossary; use its domain terms in that project's work.
- `agents/` - global agent configuration.
- `<project>/tickets/` - project work records. Workspace-level work, if any, lives in root `tickets/`.

## Agent configuration files

Global guidance is under `agents/`; project-specific guidance is under `<project>/agents/`. Each tier may contain `rules/`, `skills/`, `tools/`, `utils/`, and `roles.yaml`. Roles reference items in their own tier. A project role is named `<project>/<role>`.

The following illustrates the shape of a role entry; names are examples:

```yaml
# agents/roles.yaml
worker:
  rules:
    - rules/no-secrets.md
  skills:
    - skills/tdd/
  tools:
    - tools/jira.tool.yaml
  utils:
    - utils/dummy-script.sh
    - utils/dummy-template.md
  clis:
    - git
    - npm
  mcp_servers:
    - foo
```

## Ticket files

All of a project's work lives in one tree, keyed by ticket:

```
<project>/tickets/<ticket>/
  ticket.md                          the official ticket: tracker link, id, title; or a local slug
  spec.md                            to-spec: the plan for the whole ticket
  tasks/<task-id>/
    task.md                          YAML front matter plus task instructions and acceptance criteria
    runs/<run-id>/
      run.json                       the run's terminal state
      learnings-review.json          the human's decision on each learning
```

Task front matter identifies the source clone, roles, and blockers. The manual defines intended workflow and state semantics.

```yaml
---
status: proposed
source_clone: dummmyRepo
roles:
  - payments/APIs
blockers:
  - task: create-refund-model
  - external: "Waiting for a coworker to do something"
---
```

The YAML front matter is followed by the task description and acceptance criteria.
