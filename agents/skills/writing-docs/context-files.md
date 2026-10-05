# Agent context files

An `AGENTS.md` is loaded by every session in its scope, so each line costs every task. It is an
index, not a home for facts: it says what the scope is and points to where knowledge lives.

## Layers

The workspace `AGENTS.md` is the global tier and a project's files refine it. The more specific
wins. Put a line at the narrowest layer where every task
needs it, and never restate a line from a broader layer.

## What earns a line

- **Scope identity**: non-obvious facts about what this folder holds, in one or two sentences.
- **Pointers**: where the wiki, rules, skills, and utils for this scope live.
- **Scope-wide obligations**: genuinely cross-cutting steps every task here must take, not
  instructions for operating on a particular destination document.

Anything needed by only some tasks goes into a skill, a rule, or the wiki, and the context file
points there at most.

## Keep navigation separate from procedures

Keep broad context files focused on where work lives. Move schemas, templates, detailed directory
trees, and authoring instructions to the narrowest owning scope or skill; they should not be loaded
for unrelated tasks. Keep shared details in one reference and have each consuming skill explicitly
instruct the agent to read it when needed. Loading a skill does not imply loading every linked file.

Do not replace every removed detail with a pointer. Add a context-file pointer only when it serves
scope-wide discovery that the existing navigation or skill workflow does not already provide.

For example, a workspace `AGENTS.md` needs to identify `<project>/tickets/` as the home of work
records, but not enumerate `ticket.md`, `spec.md`, task front matter, or run records. The detailed tree belongs in a shared authoring reference, loaded by the specification and
task skills. A root pointer to that reference is redundant when those skills already require it.
Likewise, a role-entry example belongs with agent configuration, not workspace-wide navigation.

Do not add a sentence such as "This file is limited to workspace navigation." The document's
content makes that clear, and this skill owns the convention. A `FEATURES.md` entry identifies the
human-owned feature map. A glossary entry identifies the glossary without telling readers to use its
terms. A configuration-directory entry need not repeat its nested `AGENTS.md` or instruct readers
when to load it. Keep only pointers that add discovery, not instructions inferable from the index.

When reviewing a context-file refactor, check that locations remain discoverable, every consumer
loads the relocated guidance, links resolve, and the move does not change workflow or permissions.

## Glossaries

The workspace `GLOSSARY.md` contains agent-system terms shared by every project. A project's domain
language is owned at `<project>/`: use `GLOSSARY.md` for one context, or `GLOSSARY-MAP.md` to locate
glossaries for multiple bounded contexts. Knowledge is shared across the project's source clones;
a clone does not automatically constitute a bounded context.

For active terminology modeling or changes to glossary definitions, load `domain-modeling` and read
its [glossary format](../domain-modeling/references/GLOSSARY-FORMAT.md). That skill owns discovery,
the modeling workflow, and entry format; this reference owns workspace/project placement.

## Who changes them

Agents generalize poorly from their own mistakes and bloat context files with ticket-specific
lessons. Do not add to a context file, rule, or skill on your own initiative after a mistake.
Propose the change to the user with the ladder tier it passed, and edit only once they agree.
