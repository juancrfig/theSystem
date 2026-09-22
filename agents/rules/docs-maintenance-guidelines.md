# Documentation maintenance guidelines

## Write only what the code cannot say

Before writing any documentation — a wiki page, an ADR, a decisions-ledger line, or a rule —
ask whether an agent with the whole repository checked out and unlimited time to read it would
still not know this. If reading the code answers it, do not write it. Code records *what* and
*how*; it does not record *why* it is this way or that it is deliberate.

Use a second test: if someone deleted this in six months, thinking it was a mistake, would that
be a bug? If yes, it is worth a line. If no, it dies with the ticket.

Only these facts earn documentation:

- **Rejected alternatives** — an option was tried and failed for a known reason.
- **External constraints** — a client, regulation, or named person set a requirement.
- **Non-obvious deliberateness** — something that looks arbitrary is intentional for a known reason.
- **Cross-boundary facts** — a truth spans repositories, so no one codebase states it.

Dropping is the normal outcome. A ticket not always produces more docs than its commits logs.

Documentation must state the operating contract, not duplicate implementation details that an
agent can read from the relevant code when it needs to change that code. This includes endpoint
URLs, request formats, runtime dependencies, test fixtures, and test behavior; document only the
required validation outcome and where to run it.

Do not repeat scope in artifact names or nested folders when the repository hierarchy already establishes that scope.

## Choose the smallest durable artifact

When documentation is justified, use the most constrained form that can hold
it: **drop → rule → ADR → decisions-ledger line → wiki page.** A wiki page is
the last resort.

| Artifact | What limits it |
|---|---|
| **Rule** | `Prevents:` demands a real incident. A rule without one is a preference. |
| **ADR** | Requires a named rejected alternative. No decision, no file. ADRs live in `wiki/adr/`. |
| **Ledger line** | One line. The format forbids growth. |
| **Wiki page** | **Nothing.** No scarcity mechanism at all. |

Use a wiki page only for a cross-cutting fact that belongs to no single
decision or incident. Pair every ADR with a ledger line that links to it. The
ledger is the chronological index; ADRs hold the decisions that need argument.

Prevents: Unconstrained documentation expands into generic background pages
and imported templates that describe conventions the repository does not use.

Enforce with: For each new documentation file, check the tier above it. A new
wiki page must fail the ADR test and the one-line test before it is allowed. A
new ADR must name what was rejected in its own text.
