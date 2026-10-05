---
name: ingest
description: Use when the human asks to ingest project wiki/raw sources. Drafts, checks against the wiki, asks once, then writes and commits.
---

# Ingest selected project sources

Project knowledge only: work inside one project's `wiki/` (the project is a folder directly inside the workspace).
Never use a personal or global wiki. For page conventions (SCHEMA.md, index.md, log.md, page layout) follow
`agents/skills/research/llm-wiki/SKILL.md`.

## 1. Draft in private

Take only the files the human named, under `<project>/wiki/raw/`. Do not crawl for more. Read them and draft, without
showing it yet, everything worth remembering, sorted into four sections:

- Facts
- Obligations: who owes what, and by when, when the source says so
- Pending matters: open questions and uncertainties
- Contradictions: between the sources themselves

Every item cites its raw file (heading or line where possible) and its provenance: who said it, when, and where
(for example "Ana López, 2026-10-02, Teams meeting 'Q4 planning'"). Take provenance from the source; when the source
does not show it, mark it unknown. Never guess it.

## 2. Check the draft against the wiki

Read `index.md`, recent `log.md` and the relevant pages. For each drafted item decide: new, already known (drop it),
updates an existing claim, contradicts an existing claim, or makes a claim or page obsolete. Also note restructuring
the change warrants (merge, split or rename pages). If the wiki does not exist yet, propose its SCHEMA, index and log.

## 3. Show the curated proposal and ask once

Show the human one list:

- The four sections, holding only what is new or changes the wiki, each item with citation and provenance.
- Each contradiction with the wiki: the old claim and its provenance, the new claim, and your recommendation (replace,
  keep both as a pending matter, or ask).
- Updates, restructuring and deletions, each with its reason.
- The exact pages, index entries and the log line that will change.

Then stop and ask for confirmation. Nothing is written before the human confirms. If they change the proposal, show
it again.

## 4. Write and commit

- Pages hold current knowledge only, one claim per line, so `git blame` leads from any line to its commit. Replaced and
  deleted claims leave the page; their history lives in git. Unresolved contradictions stay on the page as pending
  matters.
- Update `index.md`. Append one line to `log.md`: date, raw files ingested, one-line summary.
- Never edit, move or commit raw sources.
- Commit only the wiki pages, index and log, in one commit:
  `git add -- <project>/wiki ':!<project>/wiki/raw'`, then `git commit` with nothing else staged. The commit message
  is the change record: a one-line summary, then one entry per change:

  ```text
  Payment limit: 5k -> 10k
    reason: finance approved the higher cap
    source: raw/2026-10-02-q4-planning.vtt (Ana López, 2026-10-02, Teams meeting "Q4 planning")
  ```

  Use `added`, `changed old -> new` or `deleted` for each entry. The log line needs no hash:
  `git log -- <project>/wiki` finds the commit.
- Read back the changed files and report anything that did not land.
