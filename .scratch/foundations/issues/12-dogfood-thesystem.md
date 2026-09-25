# 12: Dogfood theSystem through the orchestrator

**What to build:** changes to theSystem itself go through the orchestrator, with the same ticket,
review, verdict, and harvest as any project. This includes changes to the orchestrator, once it is
stable enough to review itself.

**Why:** today theSystem's own commits go straight to master with no reviewer. Your own system is
the richest source of real runs, and the fastest way to find where the design hurts.

**Blocked by:** 07, 08, 10, 11

**Status:** needs-decision

## Decisions

1. **How theSystem appears as a project.** Recommended: a project folder whose source clone is a
   separate clone of the theSystem repository. The workspace that runs the orchestrator is never
   the clone being changed.
2. **Bootstrap problem.** Recommended: a change to the orchestrator itself is reviewed by the last
   released orchestrator version, never by the version under change.

- [ ] Each decision above is answered.
- [ ] One real theSystem ticket completes a full run, with a verdict and a harvest decision.
- [ ] The eval score from 10 is recorded before and after that change.
