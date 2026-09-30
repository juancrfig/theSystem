# Workspace guide

This workspace contains one folder per company project. A project can contain multiple source clones.

For the human-owned functional contract, availability labels, workflow, role semantics, and execution guarantees, use `MANUAL.md`.
This file is limited to workspace navigation.

# Start here

- `MANUAL.md` - intended behavior and practical user guidance. Follow its review status and availability labels; report discrepancies instead of changing the contract to match implementation.
- `CONTEXT.md` - workspace glossary for system terminology.
- `<project>/CONTEXT.md` - project glossary; use its domain terms in that project's work.
- `agents/` - global agent configuration.
- `<project>/tickets/` - project work records. Workspace-level work, if any, lives in root `tickets/`.

## Agent configuration files

Global guidance is under `agents/`; project-specific guidance is under `<project>/agents/`. Each tier may contain `rules/`, `skills/`, `tools/`, `utils/`, and `roles.yaml`. Roles reference items in their own tier. A project role is named `<project>/<role>`.

See `agents/AGENTS.md` for the shape of a role entry.
