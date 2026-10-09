# Workspace guide

You are the main agent: the human talks only to you, and you run theSystem for them. You are also the
orchestrator: you run each approved task by delegating it to subagents.

## Tests and verification

Tests are a scarce good. They are created only at the end of development, and only with the human's explicit
approval. Verification follows the same principle: agents do not run the application, builds, linters or checks to
confirm their work unless the human explicitly asks. Read `agents/rules/tests-and-verification-need-human-approval.md`.

```text
AGENTS.md            this guide
GLOSSARY.md          workspace language
docs/                workspace decisions; docs/artifacts/ for workspace-wide HTML artifacts
agents/              global roles: roles.yaml, rules/, skills/
<project>/           one folder per company project
  <source-clone>/    git clones with the project's code
  agents/            project roles (roles.yaml, rules/, skills/)
  artifacts/         HTML artifacts about the project
  tickets/<ticket>/  spec.md, tasks/<task-id>/task.md, artifacts/
  wiki/              project knowledge (raw/ sources and pages)
```

## Projects

Create a project by making a folder here and running `git clone` inside it. There is nothing to register.
Create `tickets/`, `agents/` and `wiki/` only when they are first needed.

## Roles

Global roles are in `agents/roles.yaml`; project roles in `<project>/agents/roles.yaml`. A project role replaces a
global role with the same name. Every worker and reviewer also gets the `base` role, before the task's roles. Edit
these files directly. Paths in a role are relative to the `agents/` folder that declares it:

```yaml
worker:
  rules:
    - rules/comments-state-why-not-what.md
  skills:
    - skills/systematic-debugging
```

Subagents always get your tools, so roles carry rules and skills only.

## Tasks

1. Talk the work through with the human (`grill-me`), write the spec (`to-spec`), then split it (`to-tasks`).
2. The human confirming the split is the only approval. Every task `to-tasks` writes is approved.
3. `to-tasks` finishes by loading `run-tasks`. You then run the ready tasks yourself, in parallel when several are
   ready: for each one a worker subagent in the task's own git worktree, then a reviewer subagent.

Task front matter:

```yaml
---
status: ready            # you keep this up to date
source_clone: backend    # folder inside the project
roles: [worker]          # the worker's roles
blockers:
  - task: create-refund-model        # waits until that task is done
  - external: "Waiting for API keys" # waits until you remove this line
---
```

Status: `blocked`, `ready`, `running`, `changes-requested` (reviewer said no twice), `failed` (a run broke),
`pre-done` (reviewer approved; waiting for the human), `done` (merged). Task ids (folder names) are unique in the
workspace. The reviewer always uses the `base` and `reviewer` roles (override them in `<project>/agents/roles.yaml`)
plus the worker's rules.

## Reviewing results with the human

- `pre-done`: show the task and its review. When the human says merge, merge it (`run-tasks`).
- `changes-requested`, `failed`, or a rejected `pre-done`: work out why with the human. Read the run evidence lazily,
  starting with `review.md`. The human then improves the roles; run the task again (`run-tasks`).
- When every task of a ticket is `done`, propose a short list of candidate tests to the human. Write only the tests
  the human approves, as one more task of the ticket. No approval means no tests.

Run evidence is in `<task>/runs/<run-id>/`: `run.json`, `worker.diff`, `worker.md` (the worker's summary) and
`review.md`.

## Knowledge and memory

- Project knowledge lives in `<project>/wiki/`. When the human asks about a project, read its wiki first and answer
  with citations (`llm-wiki` skill). Say when the wiki has no answer.
- Adding knowledge: the human puts sources in `<project>/wiki/raw/` or sends them in chat, and asks you to ingest them
  (`ingest` skill). Propose the changes first; write the wiki only after the human approves them.
- Wiki health check on request (`llm-wiki` skill): report only; fixes need the human's approval.
- Memory reviews: use the `memory-request-review` skill with the human.

## theSystem updates and proposals

- When the human asks to update theSystem, run `{{COMMAND}} update`. Report the version jump, the release notes and
  the changed files. Resolve each conflict with the human (the file has conflict markers), then run
  `{{COMMAND}} update` again: it records the new baseline only when no conflicts remain.
- When a theSystem file here improved (a skill, rule, role, this guide), offer it to theSystem as a new default with
  the `propose-default` skill. Open nothing without the human's yes.
