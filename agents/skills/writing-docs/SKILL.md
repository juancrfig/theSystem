---
name: writing-docs
description: Use when creating, editing, or reviewing documentation, memory, or context files. Decide what deserves recording and where it belongs.
---

Source: https://github.com/juancrfig/hermes-agent/tree/13c238327eebfff862d9ed60593751e419989785/skills (vendored snapshot)

# Writing docs

## Write only what the code cannot say

Human-facing user manuals are an exception: users must not need to read source to operate the product. `MANUAL.md` owns the human-approved functional contract. When available, use the experimental `manual-authoring` skill for its presentation and verification workflow.

Before writing anything, ask whether an agent with the whole repository checked out and unlimited
time to read it would still not know this. If reading the code answers it, do not write it. Code
records *what* and *how*; it does not record *why* it is this way or that it is deliberate.

Use a second test: if someone deleted this in six months, thinking it was a mistake, would that be
a bug? If yes, it is worth a line. If no, it dies with the ticket.

Only these facts earn documentation:

- **Rejected alternatives**: an option was tried and failed for a known reason.
- **External constraints**: a client, regulation, or named person set a requirement.
- **Non-obvious deliberateness**: something that looks arbitrary is intentional for a known reason.
- **Cross-boundary facts**: a truth spans repositories, so no one codebase states it.

Dropping is the normal outcome. A ticket rarely produces more docs than its commit log.

State the operating contract, not implementation details an agent can read from the code when it
needs to change that code. This includes endpoint URLs, request formats, runtime dependencies, test
fixtures, and test behavior; document only the required validation outcome and where to run it.

Do not repeat scope in artifact names or nested folders when the hierarchy already establishes it.

## Keep each instruction with its owner

Apply this skill before creating, editing, or reviewing documentation, memory, or context files.

Delete statements that merely describe what the document, its title, path, or existing content
already makes clear. Keep an explicit statement only when it adds a non-obvious fact or obligation;
do not restate a document-type convention already owned by this skill.

Keep instructions for interpreting, maintaining, or using a particular document in that document,
not in the index that points to it. A navigation entry names the destination and its responsibility;
it does not copy the destination's operating policy. This keeps policy changes local to one owner.

When removing duplicated guidance, verify that the owning document contains it. Move any missing
obligation there rather than silently dropping it or adding a second copy elsewhere.

## Choose the smallest durable artifact

Use the most constrained form that can hold the fact:
**drop → rule → ADR → decisions-ledger line → wiki page.** A wiki page is the last resort.

| Artifact | What limits it |
|---|---|
| **Rule** | `Prevents:` demands a real incident. A rule without one is a preference. |
| **ADR** | Requires a named rejected alternative. No decision, no file. ADRs live in `docs/ADRs/`. |
| **Ledger line** | One line. The format forbids growth. |
| **Wiki page** | **Nothing.** No scarcity mechanism at all. |

Use a wiki page only for a cross-cutting fact that belongs to no single decision or incident. Pair
every ADR with a ledger line that links to it. The ledger is the chronological index; ADRs hold the
decisions that need argument.

Before adding a file, check the tier above it. A new wiki page must fail the ADR test and the
one-line test. A new ADR must name what was rejected in its own text.

## Agent context files

Context files are not a tier on the ladder. Before creating, editing, or reviewing an `AGENTS.md` or `CONTEXT.md`, read [context-files.md](context-files.md), including its guidance on separating navigation from procedures and avoiding redundant pointers.
