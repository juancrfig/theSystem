# 10: Eval runner and run history

**What to build:** two read paths over the run records.

- `./orchestrator eval` runs every golden ticket, compares each terminal state and each reported
  rule id with the expected ones, and prints a score table. Scores are stored with the theSystem
  commit they ran against.
- `./orchestrator runs` lists the history: ticket, terminal state, rule ids found, tokens and
  duration per role, model per role, and the human verdict (from 11).

**Why:** the eval set is the new spec, and the trace is the product (analysis 3.2, 3.8). When you
change a rule, a skill, a model, or a `SOUL.md`, you can see whether the system got better or
worse, instead of trusting your impression.

**Blocked by:** 05, 09

**Status:** ready-for-agent

- [ ] `eval` reports per golden ticket: expected state, actual state, expected and actual rule
      ids, match or miss.
- [ ] `eval` can run one ticket or all of them, and states its token cost when it finishes.
- [ ] Scores for two theSystem commits can be compared side by side.
- [ ] `runs` works with no network access and no model calls.
- [ ] Nothing in this ticket changes run behaviour. It only reads run records.
