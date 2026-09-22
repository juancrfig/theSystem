# Local work

This project's `.scratch/` is the developer's personal, gitignored work area. It can hold specs,
tickets, research, and temporary evidence across any of the project's source clones. Paths below
are relative to this `.scratch/` directory unless stated otherwise.

## Issue tracker

Create and update local Markdown files here when asked to publish a local spec or ticket. Fetch a
local ticket by reading its file. External issue trackers remain sources of record; local creation,
splitting, status changes, and completion never authorize remote writes. Keep a source ticket ID
or URL when available, without copying its mutable status or assignment. Local tasks may split one
external ticket, span several, or have no external ticket at all.

The developer chooses the breakdown, filenames, sections, and workflow. Inspect existing work and
follow their conventions; do not reorganize it to fit this template. When no convention exists,
start with `<effort>/spec.md` (if useful) and `<effort>/issues/NN-<slug>.md` per task. Use enough
information to resume: intended outcome, affected clones, acceptance criteria, dependencies, and
relevant evidence. Add detail only when the work needs it.

## Triage labels

Use a `Status:` line by default. These are the five default triage labels:

| Label | Meaning |
|---|---|
| `needs-triage` | Pending evaluation; default for a new local ticket |
| `needs-info` | Waiting for information |
| `ready-for-agent` | Specified sufficiently for an agent to execute |
| `ready-for-human` | Requires human work |
| `wontfix` | Will not be pursued |

For execution, `in-progress` and `done` are additional local states, not triage labels. `done`
means the local acceptance criteria are met and verification is recorded; it does not claim that
an external ticket is closed or a branch merged. Record dependencies separately, for example
`Blocked by:` with local file paths. Preserve a developer's explicitly chosen local workflow and
record any label mapping here so agents can interpret it consistently.

## Domain docs

Use the project's multi-context model: read `../wiki/CONTEXT-MAP.md` when present, then only the
glossaries relevant to the work. Without a map, use existing `../wiki/CONTEXT.md` and
`../wiki/index.md` for navigation. Read relevant decisions in `../wiki/decisions.md` and
`../wiki/adr/`, including context-specific ADR locations named by the map.

Use existing domain terms and flag conflicts with recorded decisions. Missing domain files do not
block local work; do not invent contexts or scaffold empty documentation. ADRs belong under the
project's `wiki/adr/`, not `docs/adr/` or `.scratch/`; local proposals can stay here until approved.

## Findings and completion

Keep decisions, constraints, and useful discoveries with the work, under `## Findings` or the
developer's equivalent notes. At ticket completion, identify what deserves durable project context.
Most implementation detail stays local; zero durable items is a valid result. Do not commit or
archive the local ticket collection into the wiki, or delete a developer's notes without their
instruction. Never put credentials or customer data in these artifacts.
