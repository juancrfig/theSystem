# ADR 0001: Run approved tasks with theSystem's own orchestrator

- **Status:** Accepted (revised 2026-10-05 to match FEATURES.md)
- **Date:** 2026-09-26

## Context

theSystem's core is the automatic execution of approved tasks: each task gets a worker run and an independent
review, with the full evidence kept so the human can diagnose failures (FEATURES.md F4, F6).

Hermes Kanban provides durable tasks, dependencies, dispatch and review transitions. But its review lifecycle
routes requested changes straight back to the worker, while theSystem stops so the human can improve the roles
before a retry. Kanban completion also does not mean a branch has been merged, which is theSystem's meaning of
done.

## Decision

theSystem's orchestrator is the only execution authority for tasks, and each task's `task.md` is its single
record. Do not put Hermes Kanban in front of or beside it.

Reconsider Kanban only if real use shows that coordinating many tasks, not executing and reviewing one, is the
bottleneck. Any reconsideration must keep one source of truth.

## Consequences

- theSystem maintains its own small dispatcher (dependency order, parallel ready tasks) and run evidence.
- Hermes Kanban may still be used for unrelated work, but it is never authoritative for theSystem tasks.
