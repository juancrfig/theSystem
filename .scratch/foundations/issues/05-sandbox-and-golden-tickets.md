# 05: Sandbox project and golden tickets (eval set v0)

**What to build:** a tiny sandbox project in the workspace (one small clone, a `CONTEXT.md`, and
a test suite that runs in seconds) and a set of golden tickets, each with a recorded expected
outcome. The set is the first eval of the whole system.

- **Clean pass:** a small feature with clear criteria. Expected: implemented, review passed.
- **One seeded violation per applicable rule:** the ticket leads naturally into the rule's
  `Prevents:` incident. Expected: the reviewer reports that rule by id.
- **Ambiguous spec:** criteria that contradict each other. Expected: the run ends as
  `spec_ambiguous`, not with a guess.
- **Infra failure:** a clone whose toolchain is missing. Expected: `infra_blocked` before any
  model call.

**Why:** nothing measures agent behaviour today (analysis 3.2). Your rule format already holds the
eval cases: no incident, no rule, so no incident, no eval. The sandbox keeps client code and
client data out of the loop while the orchestrator is young.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] The sandbox is generic, holds no client code or data, and its tests run offline.
- [ ] Every golden ticket passes the ticket validator from 04.
- [ ] Every golden ticket has an expected terminal state and, where relevant, the rule ids the
      reviewer must report.
- [ ] Each seeded violation is checked by hand once: the violating change really breaks the rule's
      `Enforce with:` steps.
- [ ] A short note explains how to add a golden ticket when a new rule is added.
