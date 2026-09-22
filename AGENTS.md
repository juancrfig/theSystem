# theSystem Workspace

This workspace holds one folder per project. Each project can contain several source clones.
Their code, build outputs, and dependencies are gitignored.

**Written for agents, not for humans**: Every file must be produced and maintained strategically to
be useful and easily navigable by agents. The user will use agents as the interface to the codebase
in most cases. Follow `agents/rules/communication-style.md` and
`agents/rules/docs-maintenance-guidelines.md` when working with documentation.

**Preflight check**: Before changing code, run `./preflight` in the target clone.
If it is missing or fails, read `agents/utils/scripts/preflight/AGENTS.md`.

**Ticket creation**: When the user wants to *create a local ticket*, create a pending ticket in the
relevant project's `.scratch/`. Read `.scratch/AGENTS.md` first. If it is absent, follow
`agents/utils/templates/scratch/AGENTS.md`.
