# Skill mechanics

What changes when the document is a skill. Everything else is in [SKILL.md](SKILL.md).

## Who can start it

- **Agent-started**: keep a `description` that lists the trigger cases. The agent and other skills can load it, and the human can still call it by name. Its cost: the description sits in every session's context.
- **Human-started**: set `disable-model-invocation: true` and write a one-line, human-facing description. It costs no context, but the human must remember it exists, and no other skill can load it.

Make a skill agent-started only when the agent or another skill must reach it on its own.

## When to split a skill

Split off a new agent-started skill only for a distinct trigger word the human actually uses, or when another skill must load it alone. Each new description adds context cost to every session. Two skills that trigger on the same case make the agent pick at random: merge them.

Reference that two human-started skills both need goes in a plain file both point to, because neither can load the other.

## Router skills

When human-started skills pile up past what the human remembers, add one human-started **router** skill that names each and when to use it. It can only point; it cannot start them.
