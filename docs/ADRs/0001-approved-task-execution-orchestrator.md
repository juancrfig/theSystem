# ADR 0001: Keep approved-task execution under theSystem's orchestrator

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

theSystem's differentiating requirement is not a durable task board; it is a bounded, auditable execution of each human-approved task. Its intended contract gives the orchestrator deterministic ownership of validation, worker/reviewer sequencing, isolation checks, Git operations, terminal states, and immutable run evidence. A run is one pass; the human decides whether findings justify another run. A task is done when its branch has been merged.

Hermes Kanban provides durable tasks, dependencies, atomic claims, dispatch, attempt history, and review transitions. But its ordinary dispatch does not itself enforce theSystem's explicit human-approval boundary or container/overlay isolation contract. Its review lifecycle uses separate implementation and reviewer runs and can route requested changes back to the worker. The documented non-Hermes CLI/container worker lane is not yet a paved integration. Kanban completion also does not itself mean a branch has been merged.

Relevant design evidence: [`AGENTS.md`](../../AGENTS.md), [tracer-bullet orchestrator run](https://github.com/juancrfig/theSystem/issues/6), and [dogfood theSystem](https://github.com/juancrfig/theSystem/issues/12). Hermes references: [Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban) and [worker lanes](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes).

## Decision

Build and use theSystem's deterministic orchestrator as the sole execution authority for approved tasks. Do not use Hermes Kanban as theSystem's task lifecycle authority, and do not add a Kanban layer in front of the orchestrator for now. Keep task approval, run state, and completion evidence in one authoritative system.

Reconsider Kanban only after the orchestrator has been used on representative work and run evidence shows that coordination across tasks—not execution containment, worker/reviewer verification, or run reliability—is a material bottleneck. Any reconsideration must preserve one source of truth and explicitly prove the required approval and execution guarantees before adopting Kanban or a hybrid.

## Rejected alternatives

- **Hermes Kanban as execution authority:** rejected because its default lifecycle does not provide theSystem's required admission, single-pass review, isolation, and merged-task completion semantics without substantial custom work.
- **Kanban plus theSystem both controlling the same tasks:** rejected because duplicate dispatch and independently maintained lifecycle state create reconciliation and accidental-execution risks.

## Consequences

- TheSystem must implement and validate its own deterministic execution path; the current `orchestrator` placeholder is not an operational substitute for Kanban.
- The planned tracer-bullet run remains the first end-to-end validation target; this ADR does not claim that orchestration is already implemented.
- Hermes Kanban may still be used for unrelated work, but it is not authoritative for theSystem-approved tasks.
- No separate Kanban-integration ticket is created now. The reconsideration trigger is evidence from real orchestrator use, not a commitment to adopt Kanban.
