---
name: to-tasks
description: Split a ticket's spec, or the current conversation, into tracer-bullet tasks with roles and blockers, then start them.
disable-model-invocation: true
---

Sources: [mattpocock/skills](https://github.com/mattpocock/skills) v1.3.1 `to-tickets` (MIT), adapted to theSystem.

# To Tasks

Split a ticket into **tasks**: tracer-bullet vertical slices that the orchestrator runs unattended. Each task names the tasks that **block** it and the roles its worker gets.

Tasks live in the ticket's folder. Read [Workspace ticket layout](references/ticket-layout.md) before creating or changing anything there.

## Process

### 1. Gather context

Work from the conversation and the ticket's `spec.md`. If the human names a ticket or spec, read it in full.

If you still need to know the current code, have a sub-agent explore it when you can delegate; otherwise explore it yourself. Use the project's glossary vocabulary and respect ADRs in the area.

Look for prefactoring that makes the work easier: "make the change easy, then make the easy change".

### 2. Draft vertical slices

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Any prefactoring comes first

</vertical-slice-rules>

Give each task its **blockers**: the tasks that must be done before it can start. A task with no blockers starts at once.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites in batches sized by blast radius (per package, per directory), each batch its own task blocked by the expand, keeping CI green because the old form still exists. Finally contract: delete the old form in a task blocked by every migrate batch. When even the batches can't stay green alone, let them share an integration branch that all block a final integrate-and-verify task; green is promised only there.

Propose each task's **roles** from the global `agents/roles.yaml` and the project's `agents/roles.yaml` (a project role replaces a global role with the same name). Every agent also gets `base` automatically, so never list it. Use `worker` when no other role fits.

### 3. Confirm the split with the human

Show the split as a numbered list. For each task:

- **Title**
- **Delivers**: the end-to-end behaviour it makes work
- **Blocked by**: the tasks that gate it, or none
- **Roles**: the proposed roles

Ask whether the granularity is right, whether each blocker genuinely gates its task, whether any task should be merged or split, and whether the roles fit. Iterate until the human confirms. That confirmation is the only approval: every task you write is approved and will run.

### 4. Write the tasks and start them

Write one `<project>/tickets/<ticket>/tasks/<task-id>/task.md` per task. The task id (its folder name) is unique in the workspace. Before running the workspace command, obtain an independent read-only readiness review of the exact task body and evidence the worker will receive. The reviewer must not rely on this conversation or an unsupplied spec. Check requirement coverage, verified starting points, accessible contract evidence, approved test cases, and feasibility with the worker's permitted tools. Resolve every implementation-critical gap before dispatch; this review verifies preparation and is not a second human approval. Only then run the workspace command's `run` (its name is in the workspace `AGENTS.md`).

## Task file

The orchestrator reads the front matter; names are examples:

```yaml
---
status: ready              # `blocked` when it has blockers; the orchestrator keeps it up to date
source_clone: backend      # folder of the git clone inside the project
roles: [worker]            # the roles the human confirmed
blockers:
  - task: create-refund-model                       # waits until that task is done
  - external: "Waiting for a coworker to do something" # waits until this line is removed
---
```

The worker and the reviewer receive only the body below the front matter: not the spec, not this conversation. Every task is **self-contained**: copy in everything the human agreed that bears on it.

### Main-agent ownership of the implementation handoff

The main agent and human resolve requirements and implementation-critical facts during preparation. The worker implements the supplied decisions; it does not rediscover the intended API, choose product semantics, or fill missing contracts with assumptions. Ordinary coding judgment and verification remain necessary, but an unstated decision needed to implement approved behavior is a handoff defect. A worker that stops rather than inventing that decision is enforcing the boundary correctly.

For each task, supply:

- **Verified starting point:** the inspected source revision and exact relevant files/symbols. Distinguish backend availability from consumer implementation. Identify what exists, what is missing, and what must be added or changed; support every consequential claim of existing functionality with evidence.
- **Exact interfaces and evidence:** applicable tools, toolsets, CLIs with commands and working directories, and API method, endpoint, service, parameter names/types, headers, request/response structures, pagination, and error behavior. Include non-sensitive producer-derived examples and their source/version or capture scope. Never substitute invented fixtures or credentials. Supply this material in the task or as explicitly delivered, readable evidence; a reference to material the worker cannot access is not a handoff.
- **Approved test cases:** exact named inputs, expected outcomes and observable assertions, their independent requirement/contract basis, the public test boundary, and execution commands/environment. Do not make the worker infer the test contract or authorize extra cases.
- **Dependencies and unknowns:** identify prerequisites and permitted access. Resolve implementation-critical unknowns before declaring the task ready. Do not disguise an unresolved lookup as an instruction to reuse something.

Include only relevant material, but do not compress away details required to build correctly. Preparation is complete when the worker can implement and verify the task without assuming missing requirements or external contracts.

<task-template>

# <Task title>

**What to build:** the end-to-end behaviour this task makes work, from the user's perspective.

**Acceptance criteria:**

- [ ] Criterion 1
- [ ] Criterion 2

**Test seams:** where the tests go, as agreed in the spec.

**Checks:** the exact commands to run before handing off (tests, lint, type check).

**Decisions and limits:** the spec decisions that bind this task, and what is out of scope for it.

**Start from:** the files or modules the work begins in.

</task-template>

Leave out a section only when it has nothing to say for this task. If a prototype produced a snippet that encodes a decision more precisely than prose (state machine, schema, type shape), inline the decision-rich part and say it came from a prototype.
