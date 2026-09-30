# Global agent configuration

This directory holds workspace-wide agent guidance and role declarations. Project-specific guidance lives under `<project>/agents/`.

## Role entries

Each tier may contain `rules/`, `skills/`, `tools/`, `utils/`, and `roles.yaml`. Roles reference items in their own tier. A project role is named `<project>/<role>`.

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
