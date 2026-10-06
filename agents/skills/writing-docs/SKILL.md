---
name: writing-docs
description: Use when writing or editing anything an agent reads later (skills, rules, AGENTS.md, docs, memory, wiki pages). Decides whether to record a fact, where it goes, and how to word it.
---

Sources: theSystem, merged with [mattpocock/skills](https://github.com/mattpocock/skills) v1.3.1 `writing-for-agents` (MIT).

# Writing docs

Three questions, in order: should this be written, where does it go, how is it worded.

## 1. Write only what the environment cannot say

Ask: would an agent with the whole repository and unlimited time to read it still not know this? If the code, a config file, the directory layout or a `--help` answers it, leave it to that lookup: a copy goes stale. Code records *what* and *how*; it does not record *why*, or that something odd is deliberate.

Second test: if someone deleted this in six months, thinking it was a mistake, would that be a bug? If not, it dies with the ticket.

Only these earn a line:

- **Rejected alternatives**: an option was tried and failed for a known reason.
- **External constraints**: a client, regulation or named person set a requirement.
- **Non-obvious deliberateness**: something that looks arbitrary is intentional for a known reason.
- **Cross-boundary facts**: a truth spans repositories, so no one codebase states it.

Dropping is the normal outcome. State the operating contract (the required outcome and where to check it), not details an agent reads from the code when it changes that code: endpoint URLs, request formats, fixtures.

User manuals are the exception: users must not need the source to operate the product. Load `manual-authoring` for them. A `FEATURES.md` is owned by the human; agents do not edit it.

## 2. Put it in the smallest durable home

**drop → rule → ADR → decisions-ledger line → wiki page.** Check the tier above before adding a file.

| Artifact | What limits it |
|---|---|
| **Rule** | `Prevents:` demands a real incident. A rule without one is a preference. |
| **ADR** | A hard-to-reverse, surprising decision with a real trade-off, in `docs/adr/`. Load `domain-modeling` for the format. |
| **Ledger line** | One line. The format forbids growth. |
| **Wiki page** | Nothing limits it: last resort, for a cross-cutting fact that belongs to no single decision or incident. |

Keep each meaning in **one owner**. Instructions for using a document live in that document; an index entry names the destination and its job, never copies its policy. When you remove a duplicate, check the owner holds it first.

`AGENTS.md`, `GLOSSARY.md` and `GLOSSARY-MAP.md` are not on the ladder: read [context-files.md](context-files.md) before touching one. When the document is a skill, read [skill-mechanics.md](skill-mechanics.md).

## 3. Word it so every run takes the same path

- **Pointers decide reach.** A skill description or an `AGENTS.md` line that names another file is a **pointer**: its wording, not the target, decides when the agent opens the material. Lead with the trigger word, give one trigger per distinct case, and cut what the body already says. Always-loaded text costs every turn, so prune pointers hardest.
- **Inline what every case needs; disclose the rest.** Put what only some cases reach in a separate file behind a pointer. Keep a concept's definition, rules and caveats under one heading. A document too long to attend to (**sprawl**) fails even when every line is true.
- **End every step on a checkable "done".** A vague end ("understand the code") invites rushing to the next step. A demanding one ("every modified model accounted for") drives the legwork. If a step still gets rushed, split the later steps into a separate hand-off.
- **Use leading words.** One familiar word the model already knows (_tight_ loop, goes _red_, _tracer bullet_) anchors a whole behaviour in one token. Repeat the word, never the explanation. Prefer an existing word to a coined one.
- **State the target behaviour.** "Don't X" puts X in front of the agent. Write what to do ("write one-line comments"); keep a prohibition only as a hard guardrail, paired with the positive.
- **Prune.** Delete any sentence that does not change behaviour compared with the model's default (a **no-op**), and any line that went stale. Delete the whole sentence, not words from it. Unpruned docs collect **sediment**: old layers nobody dares to remove.
