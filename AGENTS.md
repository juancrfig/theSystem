# <Company> Workspace

This workspace holds one folder per <company> project. Each project can contain several source clones. 
Their code, build outputs, and dependencies are gitignored. 

**Written for agents, not for humans**: Every file must be produced and maintaned strategically to 
be useful and easily nagivable by agents. When working with docs, follow `<company>/agents/rules/docs-maintenance-guidelines.md`.
The user will use agents as interface to the codebase in most cases. 
Consequentlly, you must follow `agents/rules/global/communication-style.md`.

**Preflight check**: Before changing code, run `./preflight` in the target clone.
If missing or failing read `<company>/agents/scripts/preflight/AGENTS.md`.

**Ticket creation**: When the user wants to *create a local ticket*, create a pending ticket in the relevant 
project's `/.scratch/` (read its AGENTS.md before creating a local ticket).
If absent, follow `<company>/agents/utils/templates/scratch/AGENTS.md`.
