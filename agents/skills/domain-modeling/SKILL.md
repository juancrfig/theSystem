---
name: domain-modeling
description: Use when sharpening domain terminology or modeling decisions. Challenge concepts and maintain GLOSSARY.md, glossary maps, and ADRs.
---

Source: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60/skills/engineering/domain-modeling (vendored and adapted snapshot)

# Domain Modeling

Actively build and sharpen the domain model as you design: challenge terms, probe concrete edge
cases, and capture agreed vocabulary and decisions as they crystallise. Merely reading the glossary
for vocabulary is not this skill; this skill is for changing the model, not just consuming it.

## Resolve the owning scope first

Load `writing-docs` and read its [context-files.md](../writing-docs/context-files.md) before changing
glossaries or navigation. That reference owns workspace/project placement. Read the applicable
glossary or glossary map, the relevant `MANUAL.md` contract, and ADRs before proposing changes.

The workspace is not a single source repository. Identify the owning project from workspace
navigation and the source clone's location, not merely the current working directory. If ownership
is unclear, ask. Source clones do not automatically define distinct bounded contexts.

For a single context, use `GLOSSARY.md` at the owning scope's root. For multiple contexts, use a
`GLOSSARY-MAP.md` there to locate each context's glossary and describe their relationships. Read
[GLOSSARY-FORMAT.md](references/GLOSSARY-FORMAT.md) for discovery and entry format. Create files
lazily, only when the first agreed term or qualifying decision needs recording.

## Approval boundary

Document resolved vocabulary inline within the user's authorized modeling work; do not require a
separate confirmation for every agreed term. Unresolved proposals stay in the discussion or work
record. Follow `writing-docs` approval requirements for unsolicited changes to guidance.

A documentation reorganization or naming update does not authorize changing theSystem's major
mechanisms or architecture. Before changing execution authority, isolation, role composition,
approval boundaries, tracker ownership, or run/evidence storage, explain the proposed change and
obtain explicit approval. Recording an ADR does not itself authorize implementing its decision.
Do not alter `MANUAL.md`'s functional expectations merely to fit current code.

## During the session

### Challenge against the glossary

When a term conflicts with existing language, call it out immediately: "Your glossary defines
'cancellation' as X, but you seem to mean Y. Which is it?" Do not silently replace the agreed meaning.

### Sharpen fuzzy language

When language is vague or overloaded, propose a precise canonical term: "By 'account', do you mean
the Customer or the User? Those are different concepts." Use `codebase-design` for its architectural
vocabulary when relevant, without copying general engineering terms into the domain glossary.

### Discuss concrete scenarios

Stress-test relationships with specific edge cases that force precision about concept boundaries.
Label invented scenarios as hypothetical; do not present them as observed behavior or requirements.
When a word legitimately means different things in different bounded contexts, qualify its scope
rather than forcing one global definition.

### Cross-reference with code and contract

Check claims against relevant definitions and usages across the project's source clones. Surface
contradictions between code, the glossary, and the human-owned contract; distinguish intended
behavior from observed implementation. Do not rewrite expectations merely to match the code.

### Update GLOSSARY.md inline

When a term is resolved, capture it immediately rather than batching resolved terms until the end.
Read [GLOSSARY-FORMAT.md](references/GLOSSARY-FORMAT.md) before editing. Keep definitions tight and
opinionated, with canonical terms and misleading synonyms marked `_Avoid_`.

`GLOSSARY.md` is only a glossary: no implementation details, specifications, scratch notes, operating
procedures, or implementation decisions. Preserve existing meanings unless the user resolves the
change. Group related terms when useful; do not manufacture bounded contexts to match directories.

### Offer ADRs sparingly

Offer an ADR only when all three are true:

1. **Hard to reverse**: changing your mind later has meaningful cost.
2. **Surprising without context**: a future reader will wonder why it was done this way.
3. **A real trade-off**: genuine alternatives were considered and one was chosen for specific reasons.

If any is missing, skip the ADR. If approved, read [ADR-FORMAT.md](references/ADR-FORMAT.md) before
writing it. Prefer a short decision-and-rationale paragraph; optional sections are not a checklist.
