---
name: ingest
description: Use when the human asks to ingest project sources (wiki/raw files or sent in chat). Drafts, checks against the wiki, asks once, then writes and commits.
---

# Ingest selected project sources

Project knowledge only: work inside one project's `wiki/` (the project is a folder directly inside the workspace).
Never use a personal or global wiki. For page conventions (SCHEMA.md, index.md, log.md, page layout) follow
`agents/skills/research/llm-wiki/SKILL.md`.

## 1. Draft in private

When the human sends a source in chat (pasted text, a file or a link), first save it in `<project>/wiki/raw/` as
received, under a descriptive name with its date (a link: its extracted text, with the URL on the first line). Ask
which project when it is unclear. From then on it is a raw source like any other.

Take only the files the human named or sent, under `<project>/wiki/raw/`. Do not crawl for more. Read them and draft, without
showing it yet, everything worth remembering, sorted into four sections:

- Facts
- Obligations: who owes what, and by when, when the source says so
- Pending matters: open questions and uncertainties
- Contradictions: between the sources themselves

Every item cites its source so that the citation stands on its own: raw sources are never committed, so a reader
of the wiki or of git history may never see the raw file. Describe the source, then who said what. For example:
"Teams meeting 'Q4 planning' held 2026-10-01 with 3 participants (Ana López, Carlos Ruiz, Marta Gómez). Ana López said
the limit stays at 5,000 EUR." Do not cite file names or paths. Take
provenance from the source; when the source does not show it, mark it unknown. Never guess it.

## 2. Check the draft against the wiki

Read `index.md`, recent `log.md` and the relevant pages. For each drafted item decide: new, already known (drop it),
updates an existing claim, contradicts an existing claim, or makes a claim or page obsolete. Also note restructuring
the change warrants (merge, split or rename pages). If the wiki does not exist yet, propose its SCHEMA, index and log.

## 3. Show the curated proposal and ask once

Show the human one list:

- The four sections, holding only what is new or changes the wiki, each item with citation and provenance.
- Each contradiction with the wiki: the old claim and its provenance, the new claim, and your recommendation: replace
  the old claim (the newer source usually wins), or keep both and mark the page contested.
- Updates, restructuring and deletions, each with its reason.
- The exact pages, index entries and the log line that will change.

Then stop and ask for confirmation. The human approves the list as a whole, not item by item; they may drop or
change items before approving. Nothing is written before the human confirms. If the human changes the proposal
or adds information (for example a source's author or date), check the new information as in step 2, show the revised
proposal and ask again. Only a plain "yes" to the proposal on screen lets you write.

## 4. Write and commit

- Pages hold current knowledge only, one claim per line, so `git blame` leads from any line to its commit. Replaced and
  deleted claims leave the page; their history lives in git. Unresolved contradictions stay on the page until a human
  resolves them: both claims with their source, and `contested: true` plus `contradictions: [other-page]` in the
  page's front matter. The wiki health check lists them.
- When a whole page is superseded, archive it instead of deleting it: move it to `_archive/` with its original path,
  remove it from `index.md`, and replace links to it with plain text plus "(archived)". List each archive in the
  proposal with its reason.
- Update `index.md`. Append one line to `log.md`: date, the sources ingested (described, not as paths), one-line
  summary.
- Never edit, move, rename, annotate or commit raw sources. Not even to add a header.
- Commit only the wiki pages, index and log, in one commit:
  `git add -- <project>/wiki ':!<project>/wiki/raw'`, then `git commit` with nothing else staged. The commit message
  is the change record: a one-line summary, then one entry per change:

  ```text
  Payment limit: 5k -> 10k
    reason: finance approved the higher cap
    source: Teams meeting "Q4 planning" held 2026-10-02 with 3 participants; Ana López said finance approved 10k
  ```

  Use `added`, `changed old -> new` or `deleted` for each entry. The log line needs no hash:
  `git log -- <project>/wiki` finds the commit.
- Read back the changed files and report anything that did not land.
