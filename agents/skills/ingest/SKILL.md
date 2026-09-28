---
name: ingest
description: Use when reviewing selected project wiki/raw sources for human-approved wiki ingestion.
---

# Ingest selected project sources

Build on the project-local `llm-wiki` conventions. Never use a personal/global wiki as a fallback. Resolve the registered company project first and operate only within its `wiki/` directory. This skill is available in both Hermes and Copilot experiences; it does not depend on Hermes APIs.

## Prepare a proposal, without writing knowledge

1. Require an explicit list of source files under that project's `wiki/raw/`. Resolve every path and reject symlinks or paths escaping `raw/`. Do not crawl other sources.
2. Read `wiki/SCHEMA.md`, `wiki/index.md`, and recent `wiki/log.md` when they exist; read relevant existing pages and the exact selected raw files. If the wiki is new, propose its schema/index/log setup instead of silently inventing a domain or taxonomy.
3. Show the human four distinct sections: facts supported by each source, obligations with their owners/dates if explicitly present, pending matters or uncertainties, and contradictions with existing pages or between sources. Cite each claim by relative raw path and, where feasible, heading or line. Preserve disagreement rather than choosing a winner. For a conflicting existing claim, include its original wording and provenance in the proposed page alongside the new conflicting claim; do not propose replacing or deleting that claim merely because the newly selected source disagrees. If its cited raw source was not selected, do not claim that old source has been reverified.
4. Describe exactly which existing pages, new pages, index entries, and log entries would change. Reuse relevant pages; obey the project's schema and page thresholds. An obligation is knowledge, not an approved execution task. Ensure the proposed page content actually captures each fact and obligation selected for ingestion, or explicitly say which items are omitted and why. The proposed log must not claim a fact was added to a page unless that page proposal contains it.
5. Stop and ask for explicit approval of that proposal. Presenting an extraction, advancing conversation, or approval of the source itself is not permission to edit the wiki. If the proposal changes materially, show it again and seek renewed approval.

## Apply only the approved proposal

- Recheck source contents and affected pages before writing; if either changed, return to review rather than applying a stale proposal.
- Never edit, rename, delete, or reformat raw sources. Put claims and links to their relative raw paths in wiki pages; maintain existing page provenance, conflicting statements, and links.
- Update `index.md` and append to `log.md` under the existing conventions. Do not create automatic tasks or schedule rewriting.
- Read back changed pages, index, and log, and check raw-source hashes against the pre-write snapshot. Report any incomplete update rather than claiming ingestion succeeded.

For the wider wiki conventions, consult `agents/skills/research/llm-wiki/SKILL.md` in the installed company workspace. No vector database is required.
