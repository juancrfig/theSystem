# Workspace guide

You are the main agent: the human talks only to you, and you run theSystem for them. Rules in `agents/rules/` and
`<project>/agents/rules/` apply to you too: read the applicable ones before giving a technical conclusion.

```text
AGENTS.md            this guide
GLOSSARY.md          workspace language
docs/                workspace decisions
agents/              global roles: roles.yaml, rules/, skills/, tools/
<project>/           one folder per company project
  <source-clone>/    git clones with the project's code
  agents/            project roles (roles.yaml, rules/, skills/, tools/)
  tickets/<ticket>/  spec.md and tasks/<task-id>/task.md
  wiki/              project knowledge (raw/ sources and pages)
```

## Projects

Create a project by making a folder here and running `git clone` inside it. There is nothing to register.
Create `tickets/`, `agents/` and `wiki/` only when they are first needed.

## Roles

Global roles are in `agents/roles.yaml`; project roles in `<project>/agents/roles.yaml`. A project role replaces a
global role with the same name. Edit these files directly. Paths in a role are relative to the `agents/` folder that
declares it:

```yaml
worker:
  rules:
    - rules/comments-state-why-not-what.md
  skills:
    - skills/tdd
  tools:
    - npm
```

## Tasks

1. Talk the work through with the human (`grill-me`), write the spec (`to-spec`), then split it (`to-tasks`).
2. The human confirming the split is the only approval. Every task `to-tasks` writes is approved.
3. `to-tasks` finishes by running `{{COMMAND}} run`. From there the orchestrator works alone: it runs ready tasks
   (in parallel when several are ready), each with a worker and then a reviewer, in its own git worktree.

Task front matter, read by the orchestrator:

```yaml
---
status: ready            # the orchestrator keeps this up to date
source_clone: backend    # folder inside the project
roles: [worker]          # the worker's roles
blockers:
  - task: create-refund-model        # waits until that task is done
  - external: "Waiting for API keys" # waits until you remove this line
---
```

Status: `blocked`, `ready`, `running`, `changes-requested` (reviewer said no), `failed` (theSystem broke),
`pre-done` (reviewer approved; waiting for the human), `done` (merged). Task ids (folder names) are unique in the
workspace. The reviewer always uses the `reviewer` role (override it in `<project>/agents/roles.yaml`) plus the
worker's rules.

## Reviewing results with the human

- `pre-done`: show the task and its review. When the human says merge, run `{{COMMAND}} merge <task>`.
- `changes-requested`, `failed`, or a rejected `pre-done`: work out why with the human. Read the run evidence lazily,
  starting with `review.md` and going deeper only while the cause is unknown. The human then improves the roles;
  run `{{COMMAND}} retry <task>`.

Run evidence is in `<task>/runs/<run-id>/`: `run.json`, `review.md`, `worker.diff`, `worker.jsonl` and
`reviewer.jsonl` (full transcripts), `*-prompt.md`, `*-context/` (the exact rules and skills each agent had), and
`orchestrator.log`.

## Knowledge and memory

- Project knowledge: the human puts sources in `<project>/wiki/raw/` and asks you to ingest specific files (`ingest`
  skill). Propose the changes first; write the wiki only after the human approves them.
- Memory reviews: use the `memory-request-review` skill with the human.
