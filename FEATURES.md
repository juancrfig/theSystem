# theSystem · Feature map

Human-owned. Agents edit this file only with the human's explicit approval.
Every change must reference a feature ID.

Anything not in this map is not wanted.

## Later (do not build yet)

- Wizard offers to clone an existing repo as the workspace.
- Auto-merge when the reviewer approves. This replaces `pre-done`.

---

## F1 · Install theSystem

Status: wanted
Reach: `curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash` on a fresh Ubuntu server
Outcome: a short wizard asks two things, then finishes:
  1. Workspace location. Default `~/workspace`.
  2. Company name. Default `umbrella`. This becomes the main command for using theSystem.
  After the prompts, without asking or mentioning it:
  - Creates the workspace structure:
    ```
    ~/workspace/
    ├── AGENTS.md
    ├── GLOSSARY.md
    ├── docs/
    └── agents/
        ├── rules/
        ├── skills/
        └── tools/
    ```
  - Runs `git init` in the workspace if it isn't already a git repo. Hermes needs this to find the skills.
  - Links `agents/skills/` to the harness via the cross-tool symlink `.agents/skills → ../agents/skills`. Hermes doesn't need to be installed for this. When Hermes first runs in the workspace, it shows a notice and you trust the folder once.
  - If Hermes is installed, adds two Hermes personalities and selects `main` when none is selected yet. `main` is the build-mode communication style from `agents/.harness/personalities/main.md`; `casual` adds nothing, so Hermes talks normally. Switch with `/personality casual` in a chat or `hermes config set display.personality casual`; theSystem works the same in both. A reinstall refreshes `main` from the workspace file and keeps the current selection. Without Hermes, this step is skipped; rerun the install after installing Hermes.
Not this: the wizard asks nothing else, doesn't install Hermes, and says nothing about the harness.
Proof: on a fresh Ubuntu machine, run the install, accept the defaults, then check that the tree above exists, `umbrella` runs, and Hermes lists the skills in `agents/skills/`.

## F2 · Projects

Status: open (in progress)
Meaning: a project is one of the company's products, e.g. an Android app. It can have several source clones (git repos with the actual code), e.g. frontend and backend.
  ```
  ~/workspace/
  └── android-app/          ← project
      ├── frontend/         ← source clone
      └── backend/          ← source clone
  ```
Rules:
  - A project is any folder directly inside the workspace, except theSystem's own folders (`agents/`, `docs/`).
  - A source clone is any git repo inside a project.
  - No commands and no registry. The main agent creates the folder and runs `git clone`.
  - Project subfolders are created only when first needed: `tickets/` by `to-tasks`, `agents/` for project roles, `wiki/` for knowledge.

## F3 · Roles

Status: open (in progress)
Meaning: a role is a named selection of rules, skills, tools, CLIs and MCP servers (see GLOSSARY.md).
Rules:
  - Global roles live in `agents/roles.yaml`. Project roles live in `<project>/agents/roles.yaml`.
  - A project role overrides a global role with the same name.
  - No commands. The main agent edits the roles files directly.
  - `to-tasks` picks each task's roles and lists them in the task's front matter.

## F4 · Tasks

Status: open (in progress)
Flow: talk to an agent → `to-spec` writes the spec → `to-tasks` splits it into tasks → you confirm the split → each task is written as `task.md` → run (worker, then reviewer) → merge → done.
Rules:
  - Confirming the split in `to-tasks` is the only approval. Every `task.md` it writes is already approved.
  - `task.md` is the single source of truth for a task. No second copy in orchestrator state.
  - From task generation onward, everything is automatic. When `to-tasks` finishes, it hands the tasks to the orchestrator, which:
    - runs ready tasks, in parallel when several are ready
    - holds blocked tasks until their blockers are done
    - follows dependency order
  - Each `task.md` has front matter that the orchestrator reads to handle the task programmatically. Today's fields: source_clone, roles, blockers, status.
  - Task status:
    - `blocked`: waiting on another task, or on an outside reason recorded in front matter
    - `ready`: nothing blocking it, waiting for the orchestrator
    - `running`: the worker or the reviewer is working on it
    - `changes-requested`: the reviewer rejected the work. Stops and waits for the human.
    - `failed`: the orchestrator or infrastructure broke (crash, timeout, isolation). Stops and waits for the human.
    - `pre-done` (temporary): the reviewer approved; changes wait on their branch until the human approves the merge
    - `done`: merged
  - A task blocked by another task becomes `ready` only when that task is `done`.
Not this: a separate `approve` step or command, or a "proposed" state.

## F5 · Main agent is the only human interface

Status: open (in progress)
Outcome: the human talks only to the main agent. The main agent:
  - shows `pre-done` tasks; the human says merge or don't merge
  - goes through `failed` and `changes-requested` tasks with the human
  - runs memory reviews with the human, using the `memory-request-review` skill
Reach: the main agent uses `umbrella` commands; the human never runs them.
After a rejection, failure or "don't merge":
  1. The main agent and the human work out why it happened.
  2. The human improves the roles (rules, skills, tools).
  3. The main agent retries the task.

## F6 · Run evidence

Status: open
Outcome: every run stores everything:
  - the worker's diff
  - the reviewer's findings
  - the worker's and reviewer's full transcripts
  - the exact rules, skills and tools each one had
  - orchestrator logs and errors
Use: the main agent loads evidence lazily, starting with the reviewer's findings. It goes deeper only if the cause isn't found yet, and stops as soon as it is.

## F7 · The `umbrella` command

Status: open
Outcome: three commands, all with JSON output, meant for agents:
  ```
  umbrella run          → start every ready task (to-tasks calls this when it finishes)
  umbrella merge <task> → pre-done → done, after the human OKs it
  umbrella retry <task> → changes-requested, failed or pre-done → ready
  ```
Not this: status or evidence commands (agents read `task.md` and the run folders directly), and no project, role, learning or cancel commands.

## F8 · Project knowledge

Status: open
Flow:
  1. The human puts sources in `<project>/wiki/raw/`.
  2. The human asks the main agent to ingest specific files.
  3. The agent proposes: facts, obligations, open questions and contradictions (each citing its source), plus the exact pages, index and log entries it would change.
  4. The human approves. Only then does the agent write the wiki.
Rules: knowledge is per project only. Uses the `ingest` and `llm-wiki` skills. No commands.
