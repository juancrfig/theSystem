This is the **workspace**, it holds one folder per company **project**. 
Each project can contain several **source clones**

# Start here

- CONTEXT.md - the workspace glossary: terms of the agent system itself, used in every project
- <project>/CONTEXT.md - the project's domain glossary; use its terms in code, tests, docs, and conversations with the user about that project
- agents/ - Agents global configurations
- <project>/tickets/ - the project's work: every ticket, its spec, its tasks, and their runs

## Layers and roles

Guidance lives only in two layers:

- **Global:** agents/ applies to every project.
- **Project:** <project>/agents/ applies to one project.

Each tier holds rules/, skills/, tools/, utils/, and a roles.yaml that defines its roles. 
A role lists items from its own tier. A project role is named <project>/<role>, such as dummyProject/frontend. 
The global tier always defines *base*, *worker*, *reviewer*; more roles can be added freely

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

An agent's roles apply in order, and the more specific wins: a later role replaces an earlier role's item, with a skill replaced as a whole directory.
The orchestrator builds each agent's role list from *base*, the agent's own role (*worker* or *reviewer*), and 
non-canonical roles, in that order. 
Global roles come first and project roles after, each tier keeping that order. 
For a task with the role *dummyProject/APIs*, the worker gets:

*base*, *worker*, *dummyProject/APIs*

# Tickets

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

The worktree, agent homes, and raw streams live in the run's folder only while the run is active, and are never committed.

Every task.md begins with YAML front matter. Its human-controlled status may only be *proposed* (drafted by *to-tasks*, awaiting approval), *ready-for-agent* (approved to run), *done* (the task branch has been merged), or *dropped* (intentionally abandoned).
The front matter identifies the source clone, roles, and blockers.
A blocker is either a task dependency, resolved when that task is *done*, or an external condition, resolved when a human removes it. Every *ready-for-agent* task with resolved blockers is eligible to run. All other statuses are computed and never stored: *blocked* when any blocker is unresolved, *running* when a run directory exists without `run.json`, or otherwise the terminal state of the latest run. `./orchestrator status [<ticket>]` shows these computed statuses. The workspace's own work lives in `tickets/` at the workspace root.

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

The YAML front matter is followed by the task's description and acceptance criteria.

# Agents

- **Main agent** (default Hermes profile): works with the human, plans the change, monitors the runs, 
and helps the human to improve the system
- **Worker**: writes the change. Its *worker* role holds what every worker always has
- **Reviewer**: checks the change against the rules. Its *reviewer* role holds what every reviewer always has

The worker and reviewer are ephemeral: each run gets a fresh harness home, and nothing a run learns carries over on its own. They run on any harness the orchestrator has an adapter for. Every adapter guarantees that: 
- The harness process holds the credentials on the host
- The expected configuration for the agent is boostrapped correctly. The Principle of Minimal Privilege must
be followed deterministically. An agent must not have access to a skill, tool, or file it doesn't need
- Any tool executes in the run's container

# Workflow

1. **Plan.** The main agent navigates the wiki, gathers context, and interviews the human with *grill-me* skill if needed. Once enough context is collected, the interview is over, and *to-spec* skill is invoked
2. **Tasks.** `to-tasks` turns the spec into one or more tasks, and the human approves them. A single task is a normal outcome
3. **Orchestrate.** One run of `./orchestrator` takes **one** task file. A task changes exactly one source clone; a change that spans several clones is split into one task per clone, linked by blocking edges. Tasks whose blockers are all resolved can run at the same time, one run each; a task never has two active runs. 
A run id is a timestamp plus a short random suffix, such as `20260925T101203-a1b2`, so a task's runs sort in the order they started. The orchestrator runs the worker and reviewer and owns their lifecycle deterministically: no LLM decides control flow inside it. 
The main agent adapts a run only through the orchestrator's parameters. `./orchestrator start <task>` validates the task, detaches, and prints a stable line with the run id; nothing waits on a run. `./orchestrator status` reads the run folders, and marks a run whose process died without a terminal state as `aborted`.
4. **Implement.** The worker's commands and file edits run in a per-run Docker container that mounts only the worktree it works on. The harness process and every credential stay on the host. The container bounds the blast radius: at worst the agent destroys its own container and worktree. CLIs a role lists must be in the container image, and the orchestrator checks for them before starting. MCP servers run on the host, so each MCP server a role grants deliberately reaches outside the container.
5. **Review.** The reviewer runs in a fresh container, started after the worker's container stops. Docker mounts an overlay view of the worker's worktree: the worktree is the read-only lower layer, and a throwaway upper layer receives every write. The reviewer can therefore run tests and builds, and reuses the worker's dependencies and build output, without being able to change the worker's tree. The orchestrator hashes the worker's tree before and after the review and fails the run if it changed. The run record lists every tracked file the reviewer changed in its upper layer, and flags a changed lockfile, because the reviewer then tests against dependencies the worker installed.
6. **Record.** The orchestrator writes the run record once, when the run reaches its terminal state, and the run ends. The record is the run's `run.json`: the reviewer's structured result verbatim, which is the reviewer's channel to the main agent, plus the facts only the orchestrator knows, such as the terminal state, commits, probe and hash results, and each agent's bundle. A run is a single pass: findings do not go back to the worker automatically. The human decides what happens next, such as starting another run.

A run starts from the clone's main branch as it is at that moment, and records that commit.
The orchestrator creates the run's worktree on its own branch, `agent/<ticket>/<task-id>/<run-id>`, matching the run's folder, and commits the worker's result itself; the worker never touches git history. After the run the branch stays and the worktree is deleted.
Each agent ends by writing a structured result. The orchestrator branches only on its fields, such as a status from a fixed list, and never on prose. A worker whose instructions contradict each other stops and reports the conflict in that result instead of guessing.

An agent's structured result may carry learnings, which the orchestrator copies into `run.json` as `learnings.worker` and `learnings.reviewer`. No agent sees a learning until the human approves it through the `memory-request-review` skill. This skill is also used for Hermes' pending memory requests. Because `run.json` is never edited, each decision goes into `learnings-review.json` next to it; a learning with no decision there is pending. An approved learning becomes a project rule, when the reviewer should enforce it (the run that produced it is the rule's incident), or a project skill, when it is a procedure. Workers receive it only through roles..

Rules are the contract between the two agents. The reviewer's rules must include every worker rule, and the orchestrator refuses to start a run otherwise. The reviewer may have extra rules. Skills, tools, and utils may differ freely between the two agents.
