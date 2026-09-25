# 09: Budgets and terminal states

**What to build:** every run ends in exactly one labelled terminal state, within budgets that the
orchestrator enforces. Nothing requeues silently.

Terminal states (proposed): `passed`, `changes_requested`, `spec_ambiguous`, `infra_blocked`,
`provider_error`, `budget_exhausted`, `isolation_violated`, `aborted`.

**Why:** control flow must terminate (analysis 3.7). Kanban task `t_ed81287a` has respawned 1,237
times over about 60 hours. Its failure counter stays at 0, because rate-limit and auth requeues do
not count. Rate-limit errors were also reported as "Authorization error" in 18 session titles.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] Each agent run has a wall-clock budget and a turn budget, set in `orchestrator.yaml`
      (Hermes `--run-budget`, `--max-turns`).
- [ ] Token use per agent comes from Hermes `--usage-file` and goes into the run record.
- [ ] Provider errors (429, 402, 403, 401) end the run as `provider_error`, with the HTTP status
      and the provider. They are never labelled as authorization failures unless the status is
      401.
- [ ] An implementer that reports it cannot proceed because the spec is ambiguous ends the run as
      `spec_ambiguous`, and the report quotes the conflict.
- [ ] Every golden ticket from 05 ends in its expected terminal state, or the run record shows why
      not.
