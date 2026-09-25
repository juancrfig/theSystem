This is the **workspace**, it holds one folder per company **project**. 
Each project can contain several **source clones**

# Start here

- CONTEXT.md - the workspace glossary: terms of the agent system itself, used in every project
- wiki/index.md — cross-project knowledge
- wiki/practices/knowledge-system.md - the roles of rules, skills, and the wiki 
- <project>/CONTEXT.md - the project's domain glossary; use its terms in code, tests, docs, and conversations with the user about that project
- agents/rules/ - shared rules for the worker and the reviewer: constraints the worker follows while writing a change and the reviewer checks it against. How to run a workflow belongs in a skill, not a rule
- agents/skills/ - same skills
- agents/utils/ - shared util scripts and templates
- <project>/tickets/ - the project's work: every ticket, its spec, its tasks, and their runs (see Tickets)

## Layers and roles

Guidance lives in two tiers, both in the workspace and never inside a source clone:

- **Global:** `agents/` applies to every project.
- **Project:** `<project>/agents/` applies to one project.

Each tier holds `rules/`, `skills/`, `tools/`, `utils/`, and a `roles.yaml` that defines its roles (see CONTEXT.md). A role lists items from its own tier. A project role is named `<project>/<role>`, such as `demo/frontend`. The global tier always defines `base`, `worker`, `reviewer`, `frontend`, `backend`, and `qa`; more roles can be added freely.

An agent's roles apply in order, and the more specific wins: a later role replaces an earlier role's item with the same name, meaning the same relative path, with a skill replaced as a whole directory. Items with different names never conflict, and both are kept.

The orchestrator builds each agent's role list from `base`, the agent's own role (`worker` or `reviewer`), and the task's roles, in that order. For each global role in the list, it also adds the project's role of the same name when the project defines one. Global roles come first and project roles after, each tier keeping that order. For a `demo` task with roles `frontend, demo/APIs`, the worker gets:

`base, worker, frontend, demo/base, demo/worker, demo/frontend, demo/APIs` (each project role only if the project defines it)

# Tickets

All of a project's work lives in one tree, keyed by ticket:

```
<project>/tickets/<ticket>/
  ticket.md                          the official ticket: tracker link, id, title; or a local slug for the human's own instructions
  spec.md                            to-spec: the plan for the whole ticket
  tasks/<task-id>/
    task.md                          to-tasks: clone, roles, acceptance criteria, blockers
    runs/<run-id>/
      run.json                       written once, at the run's terminal state
      learnings-review.json          the human's decision on each learning
```

The worktree, agent homes, and raw streams live in the run's folder only while the run is active, and are never committed.

A task's `Status:` in `task.md` holds only what the human decides: `proposed` (drafted by `to-tasks`, not yet approved), `ready-for-agent` (approved to run), `done` (its branch is merged into main), or `dropped`. Every other state is computed from the files and never stored: `blocked` (a blocker is not `done`), `running` (a run folder without `run.json`), or the latest run's terminal state. `./orchestrator status [<ticket>]` shows them; there is no stored status table. The workspace's own work lives in `tickets/` at the workspace root.

# Agents

- **Main agent** (`default` Hermes profile): works with the human, plans the change, and reads each run's record.
- **Worker**: writes the change. Its `worker` role holds what every worker always has.
- **Reviewer**: checks the change against the rules with the `code-review` skill. Its `reviewer` role holds what every reviewer always has.

The worker and reviewer are ephemeral: each run gets a fresh harness home, and nothing a run learns carries over on its own. They run on any harness the orchestrator has an adapter for, currently Hermes or GitHub Copilot through the Copilot SDK. Every adapter guarantees three things: the harness process holds the credentials on the host; every tool that reads or writes files or runs commands executes in the run's container; and every other tool is off unless a role grants it.

# Workflow

1. **Plan.** The main agent navigates the wiki, gathers context from the ticket (in Jira or any other tracker) or the human's instructions, and interviews the human with `grill-me`. Once the interview is over, `to-spec` writes the spec.
2. **Tasks.** `to-tasks` turns the spec into one or more tasks, and the human approves them. A single task is a normal outcome.
3. **Orchestrate.** One run of `./orchestrator` takes one task file, and only a task file. A task changes exactly one source clone and names that clone; a change that spans several clones is split into one task per clone, linked by blocking edges. Tasks whose blockers are all done can run at the same time, one run each; a task never has two active runs, and the orchestrator refuses to start one that does. A run id is a timestamp plus a short random suffix, such as `20260925T101203-a1b2`, so a task's runs sort in the order they started. The orchestrator runs the worker and reviewer and owns their lifecycle deterministically: no LLM decides control flow inside it. The main agent adapts a run only through the orchestrator's parameters. `./orchestrator start <task>` validates the task, detaches, and prints a stable line with the run id; nothing waits on a run. `./orchestrator status` reads the run folders, and marks a run whose process died without a terminal state as `aborted`.
4. **Implement.** The worker's commands and file edits run in a per-run Docker container that mounts only the worktree it works on; the worker receives only what its roles list. The harness process and every credential stay on the host. The container bounds the blast radius: at worst the agent destroys its own container and worktree. CLIs a role lists must be in the container image, and the orchestrator checks for them before starting. MCP servers run on the host, so each MCP server a role grants deliberately reaches outside the container.
5. **Review.** The reviewer runs in a fresh container, started after the worker's container stops. Docker mounts an overlay view of the worker's worktree: the worktree is the read-only lower layer, and a throwaway upper layer receives every write. The reviewer can therefore run tests and builds, and reuses the worker's dependencies and build output, without being able to change the worker's tree. The orchestrator hashes the worker's tree before and after the review and fails the run if it changed. The run record lists every tracked file the reviewer changed in its upper layer, and flags a changed lockfile, because the reviewer then tests against dependencies the worker installed.
6. **Record.** The orchestrator writes the run record once, when the run reaches its terminal state, and the run ends. The record is the run's `run.json` (see Tickets): the reviewer's structured result verbatim, which is the reviewer's channel to the main agent, plus the facts only the orchestrator knows, such as the terminal state, commits, probe and hash results, and each agent's bundle. There is no separate report file. A run is a single pass: findings do not go back to the worker automatically. The human decides what happens next, such as starting another run.

A run starts from the clone's main branch as it is at that moment, and records that commit. A blocker counts as done only once the human has merged it into main. The orchestrator creates the run's worktree on its own branch, `agent/<ticket>/<task-id>/<run-id>`, matching the run's folder, and commits the worker's result itself; the worker never touches git history. After the run the branch stays and the worktree is deleted. The orchestrator never pushes or opens a pull request: the human does, after reading the run record.

Each agent ends by writing a structured result. The orchestrator branches only on its fields, such as a status from a fixed list, and never on prose. A worker whose instructions contradict each other stops and reports the conflict in that result instead of guessing.

For each agent, the orchestrator builds a bundle from the agent's role list (see Layers and roles). It mounts the bundle read-only into the agent's container, separately from the worktree, and the run record lists each bundle's files.

A task lists at least one role. `to-tasks` writes it, and the human approves it with the rest of the task.

An agent's structured result may carry learnings, which the orchestrator copies into `run.json` as `learnings.worker` and `learnings.reviewer`. No agent sees a learning until the human approves it through the `memory-request-review` skill, which reviews them together with Hermes' pending memory requests. Because `run.json` is never edited, each decision goes into `learnings-review.json` next to it; a learning with no decision there is pending. An approved learning becomes a project rule, when the reviewer should enforce it (the run that produced it is the rule's incident), or a project skill, when it is a procedure. Workers receive it only through roles. A learning that fits neither is dropped or goes to the wiki.

Rules are the contract between the two agents. The reviewer's rules must include every worker rule, and the orchestrator refuses to start a run otherwise. The reviewer may have extra rules. Skills, tools, and utils may differ freely between the two agents.
