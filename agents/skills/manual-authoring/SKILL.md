---
name: manual-authoring
description: Use when creating or revising a human user manual.
experimental: true
---

# Human-first manuals

Produce `MANUAL.md`: the practical guide to using a product. When the scope has a `FEATURES.md`, that human-owned feature map is the functional contract; the manual explains it and never redefines it. This experimental skill is opt-in.

## Establish the contract

1. Read the existing manual, glossary, user instructions, design decisions, relevant entry points, and tests. Preserve approved requirements. Treat implementation as evidence of availability, not authority to redefine intent.
2. Separate implemented, experimental, and designed-only capabilities. Name unresolved contradictions; never quietly choose between them. A first draft awaits human review even if its commands are implemented.
3. Organize around user goals. For each workflow include prerequisites, the action, expected outcome, and consequential failures. Keep implementation detail only when the user needs it to operate safely.
4. Keep the human in charge: agents propose contract changes; humans approve them. Do not mark a draft approved merely because publication was requested.

## Design for reading, not decoration

- Use one title, a one-sentence purpose, a short linked contents list, and descriptive task headings.
- Put the shortest successful path first. Write direct sentences and short paragraphs. Remove repeated warnings without hiding the warning where it matters.
- Use **bold** for decisions and outcomes; `inline code` for literal names and values; language-tagged fenced blocks for copyable commands. No shell prompt prefixes or placeholders in runnable examples. Separate proposed interfaces into clearly labeled `text` blocks.
- Use narrow tables for comparisons and states, numbered lists for sequences, and `<details>` for optional reference material. Never collapse prerequisites, safety boundaries, or availability warnings.
- Use GitHub-native NOTE, IMPORTANT, and WARNING alerts for restrained color and emphasis. Do not rely on custom CSS, arbitrary HTML styling, or color alone; GitHub sanitizes styles. Text must carry the meaning.
- Add a diagram or image only if it reduces explanation. Prefer a small local SVG or a supported Mermaid diagram for structure and flow; use screenshots only from the real product. Give images meaningful alt text and repeat essential meaning in surrounding text. Use readable contrast in light and dark themes, and a mobile-friendly layout. No decorative stock art, badge walls, or fabricated UI screenshots.
- Keep useful content available in ordinary Markdown readers; diagrams and color must not be the only explanation.
- Be succinct without deleting guarantees, approval boundaries, failure behavior, or unresolved limitations.

## Maintain the knowledge boundary

The manual is the authority for agreed external behavior, not a second code listing or an architecture essay. Link to glossary and rationale rather than copying them. The rule against documenting code-discoverable implementation does not exclude user instructions: humans must not need to read source to operate the product.

When changing an existing manual, compare old and new sections for lost obligations. Preserve availability distinctions and open decisions. Update the `AGENTS.md` pointer if missing. Include local visual assets in publication; check whether the distribution delivers the manual and disclose any gap rather than assuming it does.

## Verify and deliver

1. Validate local links, heading anchors, fences, and shell syntax. Exercise safe commands against isolated state; syntax checks alone do not prove functionality. Never execute a live installation just to check a snippet.
2. Inspect the rendered document in its intended surface, including image legibility, tables, alerts, and command copy controls. Verify copied text when clipboard access is available. A local render is not proof of GitHub rendering. State any untested interaction.
3. Pilot the skill against the actual manual with a separate reviewer. Permit an insufficient-evidence verdict. Fix omissions in the skill or manual before acceptance.
4. Commit or publish only when requested. After pushing, read back the exact remote revision and inspect the published document. Report only checks actually performed; publishing is not human approval of the contract.
