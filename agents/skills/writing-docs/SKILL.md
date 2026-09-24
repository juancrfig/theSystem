---
name: writing-docs
description: Decide whether a fact deserves documentation and where it goes. Use before creating or editing a wiki page, an ADR, a decisions-ledger line, a rule, a project CONTEXT.md, or an agent context file (AGENTS.md at any layer).
---

# Writing docs

## Write only what the code cannot say

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

## Choose the smallest durable artifact

Use the most constrained form that can hold the fact:
**drop → rule → ADR → decisions-ledger line → wiki page.** A wiki page is the last resort.

| Artifact | What limits it |
|---|---|
| **Rule** | `Prevents:` demands a real incident. A rule without one is a preference. |
| **ADR** | Requires a named rejected alternative. No decision, no file. ADRs live in `wiki/adr/`. |
| **Ledger line** | One line. The format forbids growth. |
| **Wiki page** | **Nothing.** No scarcity mechanism at all. |

Use a wiki page only for a cross-cutting fact that belongs to no single decision or incident. Pair
every ADR with a ledger line that links to it. The ledger is the chronological index; ADRs hold the
decisions that need argument.

Before adding a file, check the tier above it. A new wiki page must fail the ADR test and the
one-line test. A new ADR must name what was rejected in its own text.

## Agent context files

Context files are not a tier on the ladder. See [context-files.md](context-files.md).
