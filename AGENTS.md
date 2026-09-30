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

### General Guidelines

- Do not create, switch to secondary Git branches unless the user explicitly requests it.
- Besides being programmatically injected by the orchestrator, rules also apply to the interactive session with the main agent. Before giving a technical conclusion, the main agent must read the applicable global and project rules. 
