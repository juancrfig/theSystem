# 04: Ticket contract the orchestrator can validate

**What to build:** a ticket format that a machine can check, and a validator that the
orchestrator runs before it spends a token. An invalid ticket is refused with a list of what is
missing, the same way a rule mismatch is refused.

**Why:** the spec is the expensive artifact (analysis 3.6). Every INST-142 failure before the
feature itself was an unstated assumption: where the spec is mounted, which workdir, which skills,
which toolchain. A ticket that states these can be checked; a ticket that implies them cannot.

**Blocked by:** None (can start immediately)

**Status:** needs-decision

## Decisions

1. **Required fields.** Recommended: project, clone, base ref, roles for each agent,
   what-to-build, acceptance criteria, blockers, status.
2. **Each criterion names its verification.** Recommended: every criterion carries `Verify:`,
   either a command or `human`. A criterion with no verification is a wish.
3. **Where the orchestrator reads tickets.** Recommended: `<project>/.scratch/<slug>/issues/`,
   which `to-tickets` already writes.
4. **Blocker check.** Recommended: the orchestrator refuses a ticket whose blockers are not
   `done`.

- [ ] Each decision above is answered.
- [ ] `to-tickets` writes the format. Its template and the validator agree, and one of them is
      the source of the other.
- [ ] The validator reports all missing or invalid fields at once, not only the first.
- [ ] Fixtures cover a valid ticket, a missing clone, a criterion without `Verify:`, and an open
      blocker.
