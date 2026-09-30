# Workspace guide

This workspace contains one folder per company project. A project can contain multiple source clones.

- `MANUAL.md` - the human-owned functional contract.
- `GLOSSARY.md` - workspace glossary for system terminology.
- `<project>/GLOSSARY.md` or `<project>/GLOSSARY-MAP.md` - project domain language.
- `docs/` - architectural decisions and verification evidence.
- `agents/` - global agent configuration.
- `<project>/agents/` - project-specific agent configuration.
- `<project>/tickets/` - project work records.

## Global workspace ticketing

GitHub is the official and sole ticketing system for global workspace work and development of theSystem: https://github.com/juancrfig/theSystem/issues. Use GitHub Issues, comments, labels, dependencies/sub-issues, pull requests, and the theSystem GitHub Project for specifications, plans, acceptance criteria, work status, blockers, handoffs, and ticket-specific verification evidence.

Do not store those records in this repository: no root `tickets/`, scratch ticket trees, local ticket/spec files, execution plans, or ticket-status/evidence ledgers. Repository documentation may link to GitHub records; `MANUAL.md`, glossaries, agent guidance, architecture, source code, and tests remain here. Keep migration audits outside the repository, publish sanitized records, and verify each GitHub write by reading back its exact target. Missing Project access is an explicit organization blocker, not permission to create a local tracker.

This policy is scoped to the global workspace and theSystem's development. Company/product projects retain their own documented tracker and execution records, including `<project>/tickets/` where required by their contract. Do not migrate their data or change orchestrator run storage under this policy.

## Git branch policy

Do not create, switch to, or otherwise use a Git branch for work unless the user explicitly requests branch use. Work on the current branch; do not create branches or worktrees merely for isolation or convention.
