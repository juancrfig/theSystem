# 08: Enforced isolation, verified on every run

**What to build:** the orchestrator verifies the isolation guarantees itself, on every run, and
does not trust configuration flags:

- The **reviewer works on its own disposable copy** of the implementer's result. The orchestrator
  hashes the implementer's tree before and after the review, and any difference fails the run.
  Because it has a copy, the reviewer can run tests and builds, which a read-only mount breaks.
- The **implementer's container** can write only its worktree. The orchestrator probes this at
  start: a write outside the worktree must fail.
- The **bundle** is read-only for both agents. It is probed the same way.

**Why:** a protection that is only described in prose is a wish, not a gate. The reviewer's
"read-only" mount was writable in all four smoke runs: the reviewer's own write probe proved it.
Copying is free, so the goal "the reviewer cannot alter what it reviews" is best met by giving it
a copy and checking hashes (analysis 3.4).

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] A reviewer that modifies its copy does not affect the implementer's branch.
- [ ] A change to the implementer's tree during review fails the run with state
      `isolation_violated`.
- [ ] A failed probe at start ends the run as `infra_blocked` before any model call.
- [ ] The probe results are part of the run record.
- [ ] A test deliberately breaks each guarantee and sees the run refused.
