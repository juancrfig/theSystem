# 03: Canonical worker profiles

**What to build:** `bootstrap` reconciles all three Hermes profiles (`default`, `implementer`,
`reviewer`) from canonical declarations in the workspace, not only `default`. Worker profiles
become neutral: they hold model and toolset settings, but no memory, no client infrastructure, and
no persistent skills. Everything task-specific reaches them per run, through the bundle.

**Why:** shared mutable state is the choke point (analysis 3.4). Today both worker profiles
hard-code one client's Docker image, volumes, and network. Both have memory enabled and carry
client memories unrelated to their role. All three profiles share one `SOUL.md` that is not the
canonical one. Skills reach profiles through persistent global symlinks, which conflicts with
per-run bundles. The rule `bootstrap-reconciles-canonical-declarations` exists, and today's
bootstrap only half follows it.

**Blocked by:** None (can start immediately)

**Status:** needs-decision

## Decisions

1. **Worker memory.** Recommended: off for `implementer` and `reviewer`. They learn only through
   rules and skills that a human approved. This also shrinks the memory-review queue.
2. **Worker `SOUL.md`.** Recommended: one per role, written for an agent reporting to the
   orchestrator, not to a human product manager. `default` keeps the current communication style.
3. **Docker image and volumes.** Recommended: remove them from profiles. The orchestrator sets
   them per run from the ticket's clone (ticket 06).
4. **Declaration shape.** Recommended: a shared base config plus a small per-profile overlay. This
   is the same overlay idea as the tiers, one level down.

- [ ] Each decision above is answered.
- [ ] Running `bootstrap` twice changes nothing the second time. A changed declaration is applied
      on the next run.
- [ ] Worker profiles contain no client names, hosts, or credentials after bootstrap.
- [ ] Adding a fourth profile to the declaration needs no bootstrap code change.
- [ ] Offline tests cover reconciliation against a temporary Hermes home, never the real one.
