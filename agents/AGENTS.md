# Global agent configuration

Seeded into a workspace's `agents/`. `roles.yaml` declares the global roles; `rules/`, `skills/` and `tools/` hold
what they reference. Project roles live in `<project>/agents/` with the same layout, and replace a global role
with the same name.

```yaml
# agents/roles.yaml
worker:
  rules:
    - rules/comments-state-why-not-what.md   # relative to this agents/ folder
  skills:
    - skills/tdd
  tools:
    - npm
```

The reviewer of a task always receives the worker's rules as well as its own.
