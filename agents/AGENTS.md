# Global agent configuration

Seeded into a workspace's `agents/`. `roles.yaml` declares the global roles; `rules/` and `skills/` hold
what they reference. Project roles live in `<project>/agents/` with the same layout, and replace a global role
with the same name.

```yaml
# agents/roles.yaml
worker:
  rules:
    - rules/comments-state-why-not-what.md   # relative to this agents/ folder
  skills:
    - skills/systematic-debugging
```

Every worker and reviewer also gets the `base` role, before the task's roles: put what every agent needs there.
The reviewer of a task always receives the worker's rules as well as its own.

The main agent delegates each task to subagents (`run-tasks` skill) and gives each one the rules and skills of its
roles. Subagents always have the main agent's tools, so a role cannot limit tools and has no `tools` field.

All agents follow `rules/tests-and-verification-need-human-approval.md`.
