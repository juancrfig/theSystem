# 11: Verdict and harvest gate

**What to build:** closing a run takes one human pass that does three jobs:

1. **Verdict:** accept, reject, or rerun, plus a one-line note. It is stored in the run record, and
   it is the real outcome label (evals on real tickets, not only golden ones).
2. **Harvest:** the reviewer's report ends with a harvest proposal that uses the `writing-docs`
   ladder (drop → rule → ADR → ledger → wiki). Zero is the normal answer. The human accepts or
   drops each item. Nothing is written without that yes.
3. **Next action:** done, or a new run with a changed ticket.

A run without a verdict stays `awaiting-verdict` and is listed by `./orchestrator runs`.

**Why:** the learning loop must be a gate, not a habit. legacy-workspace had 20 closed efforts and zero
harvests. The README already decided that humans own the feedback loop. This ticket gives that
loop a place in the pipeline (analysis 3.9). The human's attention is spent once and serves as
eval label, knowledge filter, and next step.

**Blocked by:** 06

**Status:** needs-decision

## Decisions

1. **Who presents the run.** Recommended: the main agent (`default` profile) reads the run record
   and report, shows a short summary, and records the verdict through the orchestrator. It never
   edits the record directly.
2. **Relation to memory review.** Recommended: accepted harvest items become rules, skills, or wiki
   edits in a normal commit that passes `./check`, not Hermes memory writes. Memory review stays
   for the `default` profile only (see 03).

- [ ] Each decision above is answered.
- [ ] A verdict cannot be recorded for a run that is not in a terminal state.
- [ ] Harvest items that are accepted show which ladder tier they passed.
- [ ] `./orchestrator runs` shows open verdicts first.
