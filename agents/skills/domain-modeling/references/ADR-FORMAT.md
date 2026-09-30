# ADR format

Adapted from upstream `ADR-FORMAT.md` at the revision recorded in [SKILL.md](../SKILL.md).

## Location and numbering

Use `docs/adr/` in the owning workspace, project, or mapped bounded context. Create the directory
only when the first qualifying ADR is needed. Scan its existing numbered ADRs and increment the
highest number: `0001-slug.md`, `0002-slug.md`, and so on. A context-specific ADR records a decision
owned by that context; the scope's root ADRs record system-wide decisions.

## Minimal template

```md
# {Short title of the decision}

{One to three sentences: context, chosen approach, and why it was chosen.}
```

An ADR can be a single paragraph. Record the decision and its rationale, not a template full of
empty sections. No separate decisions-ledger entry is required. Keep ticket plans, progress, and
verification records in their scope's official tracker rather than turning ADRs into work logs.

## Optional sections

Include only when they add information:

- **Status** (`proposed`, `accepted`, `deprecated`, or `superseded by ADR-NNNN`) when decisions are revisited.
- **Considered options** when rejected alternatives are worth remembering.
- **Consequences** for non-obvious downstream effects.

Retain useful content in existing ADRs; adopting this format does not require rewriting them.

## Examples of qualifying decisions

Subject to all three ADR criteria in [SKILL.md](../SKILL.md): architectural shape, integration between
bounded contexts, technology choices with substantial lock-in, ownership boundaries, deliberate
deviations from an obvious approach, and external constraints that forced a real trade-off.

A routine library choice, reversible naming adjustment, or obvious implementation step is not an ADR.
