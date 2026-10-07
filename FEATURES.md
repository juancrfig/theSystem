# theSystem · Feature map

Human-owned. Agents edit this file only with the human's explicit approval.
Every change must reference a feature ID.

Anything not in this map is not wanted.

## Later (do not build yet)

- Wizard offers to clone an existing repo as the workspace.
- Auto-merge when the reviewer approves. This replaces `pre-done`.
- Explainer videos: on request, the main agent makes a narrated, 3Blue1Brown-style video that explains a topic. Narration uses ElevenLabs or a free alternative that runs locally.
- Configuration for the `worker` and `reviewer` profiles: their own variations of the main agent's canonical config, applied by the installer.

---

## F1 · Install theSystem

Status: wanted
Reach: `curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash` on a fresh Ubuntu server
Outcome: a short wizard asks two things, then finishes:
  1. Workspace location. Default `~/workspace`.
  2. Company name. Default `umbrella`. This becomes the main command for using theSystem.
  After the prompts, without asking or mentioning it:
  - Clones theSystem to `~/theSystem`, or reuses the clone already there, and installs the latest release (F10) from it. The release is read straight from git, so the clone's checked-out branch and working files are never touched. `install --dev` installs the working tree of the clone it runs from instead; it is for theSystem development and tests.
  - Records the workspace's baseline (F10): the release tag and a copy of the files that release shipped.
  - Creates the workspace structure:
    ```
    ~/workspace/
    ├── AGENTS.md
    ├── GLOSSARY.md
    ├── docs/
    └── agents/
        ├── rules/
        └── skills/
    ```
  - Runs `git init` in the workspace if it isn't already a git repo. Hermes needs this to find the skills.
  - Links `agents/skills/` to the harness via the cross-tool symlink `.agents/skills → ../agents/skills`. Hermes doesn't need to be installed for this. If Hermes is installed, the wizard also trusts the workspace (`hermes skills trust`), because Hermes loads repo-local skills only from trusted folders. It also makes the workspace the main agent's working folder (`terminal.cwd`), so every main-agent session (Telegram, cron and CLI) loads the workspace skills and `AGENTS.md`. theSystem ships no `hermes-agent` skill: a workspace copy would shadow the one Hermes bundles and keeps current with `hermes update`.
  - If Hermes is installed, adds two Hermes personalities and selects `main` when none is selected yet. `main` is the build-mode communication style from `agents/.harness/personalities/main.md`; `casual` adds nothing, so Hermes talks normally. Switch with `/personality casual` in a chat or `hermes config set display.personality casual`; theSystem works the same in both. A reinstall refreshes `main` from the theSystem being installed and keeps the current selection. Without Hermes, this step is skipped; rerun the install after installing Hermes.
  - Starts the artifact library (F9) as an always-on user service that survives reboots. Skipped where there is no systemd user session.
  - If Hermes is installed, gives the main agent theSystem's canonical Hermes config (`agents/.harness/canonical_config.yaml`, same shape as Hermes' own `config.yaml`) and turns on its toolsets (`agents/.harness/required_toolsets.txt`) for the CLI and Telegram. Every install resets these settings to the harness files. Auxiliary models are the only thing left to configure by hand.
  - If Hermes is installed, creates empty `worker` and `reviewer` Hermes profiles (`agents/.harness/canonical_profiles.txt`) when they don't exist yet. They inherit the main agent's credentials: they share its login store, and get a copy of its API keys on every install, without messaging-channel credentials such as the Telegram bot token. The orchestrator runs workers and reviewers in them (F4).
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
Meaning: a role is a named selection of rules, skills and tools (see GLOSSARY.md).
Rules:
  - Global roles live in `agents/roles.yaml`. Project roles live in `<project>/agents/roles.yaml`.
  - A project role overrides a global role with the same name.
  - Every agent also gets the `base` role, before the task's roles.
  - No commands. The main agent edits the roles files directly.
  - `to-tasks` picks each task's roles and lists them in the task's front matter.
  - `tools` lists Hermes toolsets (`terminal`, `file`, `web`, `browser`, ...). The agent gets only those, enforced by Hermes. A role without `tools` gets no tools. CLIs are not declared: whatever is installed can run. MCP servers are not part of roles yet.

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
  - Each `task.md` has front matter that the orchestrator reads to handle the task programmatically. Fields: source_clone, roles, blockers, status, and optional `branch` and `commit_message`. The defaults are `thesystem/<task-id>` and `<task-id>: worker run <run-id>`; set task-specific values such as `feature/<descriptive-name>` and `feature: <descriptive-summary>`. Branch names must be valid and unique within a source clone; `commit_message` must be non-empty. Retries reuse the task branch and keep its prior commits; the reviewer checks the worker's exact commit, and merge uses the branch recorded for the approved run.
  - The worker runs in the `worker` Hermes profile and the reviewer in the `reviewer` profile.
  - Before either agent, the orchestrator snapshots `<project>/agents/bootstrap/<source_clone>` once, where `source_clone` is the task's single relative source-clone folder name. If the executable exists, the same exact bytes are run before the worker and reviewer in their respective worktrees; the snapshot is kept in run evidence, independent of source-clone git history and worker edits. It sets `THESYSTEM_BOOTSTRAP_ROLE` to `worker` or `reviewer`; `THESYSTEM_BOOTSTRAP_TIMEOUT` sets the finite positive timeout in seconds (default 300), and timeout kills the bootstrap process group. An absent script has no effect. Script stdout/stderr are discarded; run evidence records role and status plus exit code or timeout. Project bootstrap scripts are trusted local configuration, not a sandbox: they inherit the process environment. They must leave tracked worktree files unchanged; ignored or untracked generated artifacts are not cleaned, and non-ignored untracked files remain available to the worker.
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
  - Memory changes need the human's approval. Skill changes apply directly, and the Curator maintains the skills the agent creates.
Reach: the main agent uses `umbrella` commands; the human never runs them.
After a rejection, failure or "don't merge":
  1. The main agent and the human work out why it happened.
  2. The human improves the roles (rules, skills, tools).
  3. The main agent retries the task.

## F11 · Hermes run awareness

Status: wanted
Outcome: theSystem supplies a Hermes integration through its installer and updates. In the main agent's Ink TUI, a small panel above the status bar automatically shows the current workspace's active runs and whether the worker or reviewer is working. Finished results remain visible until dismissed.
Rules:
  - Label these as theSystem runs, not native Hermes subagents. The main agent can discover active runs and inspect their status without the human supplying paths.
  - Each run ending in `pre-done`, `changes-requested`, or `failed` automatically signals the main-agent session that dispatched it. A busy session queues the signal; an idle session starts a turn. The launcher's exit is not a run-completion signal.
  - Keep undelivered events across restarts and protect against duplicate notices. Target only the originating session and profile; do not redirect to an unrelated conversation when it is unavailable.
  - Treat a running record without a live orchestrator as possibly stale. Display and discovery do not repair task state.
  - Notifications never merge, retry, or approve work. Existing human approval gates remain unchanged.
  - Own the integration in theSystem's source, not a workspace-only customization. Use supported Hermes extension interfaces; no Hermes core modifications in this feature.
Proof: install in a temporary workspace and main-agent profile; dispatch a controlled run; see worker/reviewer progress in the TUI and through agent discovery; end it with each terminal outcome and receive a turn in the originating session without user input. Confirm busy-session queueing, unavailable-session retention and restart recovery, duplicate protection, stale-run labeling, and dismissal of finished results. Confirm no task mutation, merge, retry, cross-profile delivery, or notification caused solely by launcher exit.

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
Outcome: four commands, all with JSON output, meant for agents:
  ```
  umbrella run          → start every ready task (to-tasks calls this when it finishes)
  umbrella merge <task> → pre-done → done, after the human OKs it
  umbrella retry <task> → changes-requested, failed or pre-done → ready
  umbrella update       → install the latest theSystem release and merge it into the workspace (F10)
  ```
Not this: status or evidence commands (agents read `task.md` and the run folders directly), and no project, role, learning or cancel commands.

## F8 · Project knowledge

Status: open
Outcome: the main agent knows each project. It answers questions from the project wiki, adds knowledge from sources the human gives it, and checks the wiki's health.
Ingest:
  1. The human puts sources in `<project>/wiki/raw/`, or sends them in chat (link, file or pasted text); the agent saves those in `raw/`.
  2. The human asks the main agent to ingest specific files.
  3. The agent proposes: facts, obligations, open questions and contradictions (each citing its source), plus the exact pages, index and log entries it would change.
  4. The human approves the list as a whole (not item by item). Only then does the agent write the wiki.
Answer: when the human asks about a project, the main agent reads its wiki first and answers with citations. It says when the wiki has no answer. It may offer to save a valuable answer as a page, with approval.
Health check: on request, the agent reports broken links, orphan and missing pages, stale and contested pages. Fixes go through the same approval.
Rules:
  - Knowledge is per project only. Uses the `ingest` and `llm-wiki` skills. No commands.
  - Raw sources are never edited and never committed. Citations name no file or path: each describes its source and who said what, so it stands on its own, e.g. "Teams meeting 'Q4 planning' held 2026-10-01 with 3 participants. Ana López said the limit stays at 5,000 EUR."
  - A superseded page moves to `_archive/` and leaves the index; it is not deleted.
  - Contradictions: the agent recommends replacing the old claim (the newer source usually wins) or keeping both. Kept contradictions stay on the page, marked contested, until a human resolves them.
  - When the human changes the proposal or adds information, the agent shows the revised proposal and asks again.
Proof: in a sample project, ingest a meeting transcript and an email that contradicts it; approve; then send a third source in chat that contradicts the wiki, change the proposal to keep both, approve. Check that raw files are unchanged and uncommitted, citations name no paths, the contested page is marked, and each ingest is one commit. Ask a question the wiki answers and one it does not. Run a health check on a wiki with a broken link: it reports and changes nothing.

## F9 · Artifact library

Status: wanted
Reach: open `http://localhost:8765` on the server. The installer starts it (F1).
Outcome: one minimal page lists every HTML artifact the agents made, so the human can browse and review them:
  - Recent first, then grouped by project and by ticket, with a filter box.
  - Artifacts live in `<project>/tickets/<ticket>/artifacts/`, `<project>/artifacts/`, or `docs/artifacts/` for workspace-wide work.
  - The `main` personality saves every artifact there and replies with its link.
Not this: no Tailscale, SSH tunnels or remote access (localhost only), no database, no commands, no editing from the page.
Proof: save an HTML file in a ticket's `artifacts/`, open `http://localhost:8765`, check it is listed under its project and ticket, and click it open.

## F10 · Shared improvements

Status: wanted
Meaning: improvements made in one workspace reach theSystem, and theSystem's improvements reach every workspace.
  - Up: the main agent offers a workspace improvement as a new theSystem default (a proposal).
  - Down: `umbrella update` brings a workspace to the latest release, keeping its local edits.
Releases:
  - Numbered GitHub Releases, `vMAJOR.MINOR`. Installs and updates use the latest release, never unreleased work on `master`. Existing three-part tags remain unchanged.
  - Increment MINOR for each release; increment MAJOR and reset MINOR to zero for breaking changes.
  - An owner's request to push theSystem also authorizes a release, unless they explicitly exclude it. After checks, commit, push and publish without a second confirmation. Notes cover all changes since the prior release, including direct commits; planned functionality is not described as implemented. Verify publication and report its link; publication does not automatically update workspaces.
  - Our own development keeps pushing straight to `master`. Only proposals use pull requests.
Baseline:
  - theSystem owns exactly the files seeded from the repo's `workspace/` (into the workspace root) and `agents/` (into the workspace `agents/`). Project folders, `.thesystem/` and Hermes memory are never included.
  - The workspace records the release it was installed or last updated from in `.thesystem/baseline/`: the tag and a copy of the files that release shipped, after the install's substitutions (`{{COMMAND}}` becomes the company command).
  - One clone per server, `~/theSystem`, serves installs, updates and proposals.
Update (`umbrella update`, run by the owner in a terminal or by the main agent in chat):
  1. Re-applies the wizard's silent steps from the new release: installed program, canonical Hermes settings, toolsets, personalities, profiles and the artifact library service.
  2. Merges every theSystem file: baseline (base), workspace file (local) and new release file (theirs), with git's file merge.
     - unchanged locally → take the new version; unchanged upstream → keep the local file
     - both changed → merge; on a clash, write conflict markers and report a conflict
     - new upstream file → add it; a different local file at that path is a conflict
     - removed upstream → remove it if unchanged locally; if changed locally, conflict and keep it
     - removed locally → stays removed if unchanged upstream; if changed upstream, conflict
  3. Every non-conflicting file is updated even when others conflict. The main agent resolves conflicts with the owner in chat. The new baseline is recorded only when no conflict markers remain: until then each run of `umbrella update` reports the open conflicts again.
  - Output (JSON): from and to versions, the release notes in between (GitHub Releases, or the tag annotations when GitHub can't be reached), files updated, added, removed and merged, conflicts, and whether the baseline was recorded.
  - Already on the latest release with nothing pending: reports "up to date" and changes nothing.
  - No baseline yet (installed before baselines existed): identical files are adopted silently, differing files are conflicts showing both versions, and the baseline is recorded once they are resolved.
Proposals (`propose-default` skill, at any time, inside or outside a memory review):
  - Candidates are theSystem files that differ from the baseline: changed, added in global `agents/`, or deleted.
  - One pull request per improvement, labeled (`skills`, `rules`, `roles`, `wizard`, `orchestrator`, `fix`), with a "what and why" description.
  - Written in terms of theSystem's own files: `{{COMMAND}}` instead of the company command.
  - Before opening it, the main agent checks the change for company information (client, project and people names, internal URLs, secrets) and shows the owner anything flagged. The pull request opens only after the owner says yes.
  - Opened from its own branch in a temporary git worktree of `~/theSystem` based on `master`, so the clone's checkout is never disturbed.
Not this: automatic or scheduled updates, "you are behind" checks, proposing Hermes memory, personal skills or anything in a project folder, or carrying Hermes settings changed by hand with `hermes config set`.
Proof: in a temporary repo with release tags standing in for GitHub, install, publish a new release that changes, adds and removes files, edit the workspace on both sides, run `umbrella update`, and check the merged files, the reported conflicts, the release notes and that the baseline is recorded only after the conflicts are resolved. Check that the clone's branch and working files are unchanged. List proposal candidates and check that changed, added and deleted files are found, project folders and `.thesystem/` are ignored, and `{{COMMAND}}` is restored.
