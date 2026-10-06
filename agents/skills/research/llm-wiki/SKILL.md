---
name: llm-wiki
description: "Use when answering from, checking, or setting conventions for a project wiki. Writing sources into it is the ingest skill."
version: 2.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [wiki, knowledge-base, research, notes, markdown, rag-alternative]
    category: research
    related_skills: [ingest]
---

Source: Hermes Agent's bundled `llm-wiki` (MIT), adapted to theSystem.

# Project wiki

A persistent, compounding knowledge base of interlinked markdown files, after
[Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): knowledge is
compiled once and kept current, instead of rediscovered on every question.

This skill owns the wiki's **conventions**, **answering questions** from it and the **health check**. Every write
that adds sources (including creating a new wiki) goes through the `ingest` skill: it drafts, asks the human once,
then writes and commits under the conventions below.

## Location and layout

Each project has its own wiki at `<project>/wiki/`. There is no global wiki; if the project is unclear, ask.

```
wiki/
├── SCHEMA.md       # domain, conventions, tag taxonomy
├── index.md        # every page, by type, one line each
├── log.md          # one line per write, append-only
├── raw/            # sources as received: never edited, never committed
├── entities/       # people, orgs, products
├── concepts/       # topics
├── comparisons/    # side-by-side analyses
└── queries/        # answers worth keeping
```

The folder works as an Obsidian vault as is: `[[wikilinks]]` and front matter render there.

## Orient first

Before any operation, read `SCHEMA.md`, `index.md` and the last 20–30 lines of `log.md`. For a wiki over 100 pages,
also search the pages for the topic at hand. This prevents duplicate pages, missed cross-references and broken
conventions.

## Conventions

### SCHEMA.md template

Adapt to the user's domain. The schema constrains agent behavior and ensures consistency:

```markdown
# Wiki Schema

## Domain
[What this wiki covers — e.g., "AI/ML research", "personal health", "startup intelligence"]

## Conventions
- File names: lowercase, hyphens, no spaces (e.g., `transformer-architecture.md`)
- Every wiki page starts with YAML frontmatter (see below)
- Use `[[wikilinks]]` to link between pages (minimum 2 outbound links per page)
- When updating a page, always bump the `updated` date
- Every new page must be added to `index.md` under the correct section
- One claim per line, so `git blame` leads from any line to its commit
- **Provenance:** Every claim cites its source in words, never as a file name or path: what the source
  is, when, who took part, and who said what (e.g. "Teams meeting 'Q4 planning' held 2026-10-01 with
  3 participants. Ana López said the limit stays at 5,000 EUR."). Raw files are not committed, so a
  path would point to nothing.

## Frontmatter
  ```yaml
  ---
  title: Page Title
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
  type: entity | concept | comparison | query | summary
  tags: [from taxonomy below]
  sources: ["Teams meeting 'Q4 planning', 2026-10-01"]   # described, never paths
  # Optional quality signals:
  confidence: high | medium | low        # how well-supported the claims are
  contested: true                        # set when the page has unresolved contradictions
  contradictions: [other-page-slug]      # pages this one conflicts with
  ---
  ```

`confidence` and `contested` are optional but recommended for opinion-heavy or fast-moving
topics. The health check surfaces `contested: true` and `confidence: low` pages for review so weak claims
don't silently harden into accepted wiki fact.

## Tag Taxonomy
[Define 10-20 top-level tags for the domain. Add new tags here BEFORE using them.]

Example for AI/ML:
- Models: model, architecture, benchmark, training
- People/Orgs: person, company, lab, open-source
- Techniques: optimization, fine-tuning, inference, alignment, data
- Meta: comparison, timeline, controversy, prediction

Rule: every tag on a page must appear in this taxonomy. If a new tag is needed,
add it here first, then use it. This prevents tag sprawl.

## Page Thresholds
- **Create a page** when an entity/concept appears in 2+ sources OR is central to one source
- **Add to existing page** when a source mentions something already covered
- **DON'T create a page** for passing mentions, minor details, or things outside the domain
- **Split a page** when it exceeds ~200 lines — break into sub-topics with cross-links
- **Archive a page** when its content is fully superseded — move to `_archive/`, remove from index

## Entity Pages
One page per notable entity. Include:
- Overview / what it is
- Key facts and dates
- Relationships to other entities ([[wikilinks]])
- Source references

## Concept Pages
One page per concept or topic. Include:
- Definition / explanation
- Current state of knowledge
- Open questions or debates
- Related concepts ([[wikilinks]])

## Comparison Pages
Side-by-side analyses. Include:
- What is being compared and why
- Dimensions of comparison (table format preferred)
- Verdict or synthesis
- Sources

## Update Policy
Pages hold current knowledge only. A newer source usually replaces the old claim, and the old one leaves the
page: its history lives in git. When it is genuinely unclear which is right, keep both claims with their sources,
set `contested: true` and `contradictions: [other-page]`, and leave them until a human resolves them.
```

### index.md Template

The index is sectioned by type. Each entry is one line: wikilink + summary.

```markdown
# Wiki Index

> Content catalog. Every wiki page listed under its type with a one-line summary.
> Read this first to find relevant pages for any query.
> Last updated: YYYY-MM-DD | Total pages: N

## Entities
<!-- Alphabetical within section -->

## Concepts

## Comparisons

## Queries
```

**Scaling rule:** When any section exceeds 50 entries, split it into sub-sections
by first letter or sub-domain. When the index exceeds 200 entries total, create
a `_meta/topic-map.md` that groups pages by theme for faster navigation.

### log.md

One line per write, newest last: `- YYYY-MM-DD <action> | <sources, described> | <one-line summary>`. Actions:
`ingest`, `health-check`, `query`. When the file passes 500 lines, rename it `log-YYYY.md` and start a new one.

### Page rules

- Create pages only past the Page Thresholds; a passing mention gets no page.
- Every page links to at least 2 others with `[[wikilinks]]`, and appears in `index.md`.
- Tags come from the taxonomy; add a new tag to `SCHEMA.md` first.
- Keep a page readable in 30 seconds; split it past 200 lines.
- A fully superseded page moves to `_archive/` with its original path, leaves `index.md`, and links to it become
  plain text plus "(archived)".

## Answering questions

1. Read `index.md` to find the relevant pages; in a wiki over 100 pages, also search page content.
2. Read those pages and answer from them, citing each page you used: "Based on [[page-a]] and [[page-b]]…".
3. Say when the wiki has no answer. Do not fill the gap from memory; name the missing knowledge as a source to
   ingest.
4. If the answer is a substantial synthesis, offer to save it in `queries/` or `comparisons/`. Write it only after
   the human approves, under `ingest`'s write and commit rules.

## Health check

Read and report only. Group findings by severity, with page paths and a suggested fix for each:

1. Broken `[[wikilinks]]`, pointing to pages that do not exist.
2. Orphan pages, with no inbound links.
3. Pages missing from `index.md`, or index entries with no page.
4. Contested pages (`contested: true` or `contradictions:`), and pages that share entities but state different facts.
5. Stale pages: `updated` more than 90 days older than the newest source on the same entities.
6. Weak claims: `confidence: low`, or one source and no `confidence` set.
7. Missing front matter fields, tags outside the taxonomy, pages over 200 lines, `log.md` over 500 lines.

Fixes are proposed as one list. Write them only after the human approves, under `ingest`'s write and commit rules,
and append one `health-check` line to `log.md`.
