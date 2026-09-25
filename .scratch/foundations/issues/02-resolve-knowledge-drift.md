# 02: Resolve knowledge drift in skills and context files

**What to build:** each fact about the agent system is stated in exactly one place, and every
other file points to it. After this ticket, an agent that reads any skill gets the same tier model,
tracker policy, and verification commands as `AGENTS.md`.

**Why:** DRY applies to knowledge (analysis 3.5). The drift found today:

- `code-review` describes a third, clone-scoped rule tier, walks the filesystem for rules, and
  requires `./preflight`. `AGENTS.md` says there are two tiers, never inside a clone. Under the
  orchestrator, the reviewer receives its rules as a bundle, and preflight was removed with the
  unreviewed utils.
- `to-spec` says "do not publish externally unless asked", then "publish it to the project issue
  tracker and apply `ready-for-agent`".
- `triage` assumes an external tracker, labels, and an `.out-of-scope/` base that this workspace
  does not have.
- The memory-review spec says the criteria live in a global rule. The implementation moved them to
  `criteria.json`.
- The vendored skills record no upstream source or version.

**Blocked by:** 01 (so the fixes land under the pointer check)

**Status:** needs-decision

## Decisions

1. **Where does the tier model live?** Recommended: only in `AGENTS.md`. Skills say "use the
   rules you were given" and point there.
2. **`code-review` under the orchestrator.** Recommended: the reviewer reviews against the
   bundle's rules and the ticket, not a filesystem walk. Keep the Standards and Spec axes.
3. **`triage`.** Recommended: remove it until an external tracker is part of the workflow. It has
   no caller in the documented workflow.
4. **Vendored skills.** Recommended: add one `Source:` line per vendored skill (upstream URL and
   commit), so you can diff against upstream on purpose instead of drifting by accident.

- [ ] Each decision above is answered, and its outcome is applied.
- [ ] No skill states the tier model. Each points to `AGENTS.md`.
- [ ] `to-spec` has one tracker policy, the same as `to-tickets`.
- [ ] The memory-review spec (local) and the skill agree on where criteria live.
- [ ] `./check` passes.
