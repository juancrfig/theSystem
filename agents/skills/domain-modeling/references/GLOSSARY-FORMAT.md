# GLOSSARY.md format

Adapted from upstream `GLOSSARY-FORMAT.md` at the revision recorded in [SKILL.md](../SKILL.md).
Workspace/project placement is owned by [writing-docs/context-files.md](../../writing-docs/context-files.md).

## Structure

```md
# {Context name}

{A short description, only if the title and location do not already establish the scope.}

## Language

**Order**: A customer's request to purchase goods.
_Avoid_: purchase, transaction.

**Invoice**: A request for payment issued to a customer.
_Avoid_: bill, payment request.
```

## Rules

- Be opinionated: choose one canonical word for each concept and list misleading synonyms under `_Avoid_`.
- Keep definitions to one or two sentences. Define what the concept is, not its execution procedure.
- Include only concepts specific to the domain. General programming and architectural vocabulary
  belong in their owning skills, not here.
- Exclude implementation details, workflow guarantees, configuration precedence, and design rationale.
  Those belong in the functional contract, owning configuration guidance, or a qualifying ADR.
- Group terms under subheadings when natural clusters emerge; a flat list is sufficient otherwise.
- Do not add placeholders or unresolved proposals. Preserve agreed meanings during format changes.

## Single versus multiple contexts

Read the owning scope's `GLOSSARY-MAP.md` if it exists; follow its links to the relevant context.
Otherwise read its root `GLOSSARY.md`. If neither exists, create `GLOSSARY.md` lazily when the first
term is resolved. If the topic's context is unclear, ask.

Use a map only when there are genuinely distinct domain contexts, not merely multiple source clones.
Project knowledge remains shared across its clones; glossary locations may follow existing context
ownership, including a source directory when it genuinely owns that domain context. Do not infer or
change runtime/service boundaries from documentation structure.

```md
# Glossary map

## Contexts

- [Ordering](ordering/GLOSSARY.md): receives and tracks customer orders.
- [Billing](billing/GLOSSARY.md): generates invoices and processes payments.

## Relationships

- **Ordering → Billing**: Billing invoices completed orders supplied by Ordering.
```

Relationship entries describe the existing domain model. Record integration trade-offs in ADRs;
do not use a map to introduce unapproved event flows, shared types, or service ownership changes.
