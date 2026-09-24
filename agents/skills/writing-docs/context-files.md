# Agent context files

An `AGENTS.md` is loaded by every session in its scope, so each line costs every task. It is an
index, not a home for facts: it says what the scope is and points to where knowledge lives.

## Layers

The workspace `AGENTS.md` is the global tier, a project's files refine it, and a clone's files
refine the project. The more specific wins. Put a line at the narrowest layer where every task
needs it, and never restate a line from a broader layer.

## What earns a line

- **Scope identity**: what this folder holds, in one or two sentences.
- **Pointers**: where the wiki, rules, skills, and utils for this scope live.
- **Scope-wide obligations**: a step every task here must take, stated once, with a pointer to
  the file that explains it.

Anything needed by only some tasks goes into a skill, a rule, or the wiki, and the context file
points there at most.

## CONTEXT.md

Each project has one `CONTEXT.md` at `<project>/CONTEXT.md`: the glossary of its domain terms,
shared by all of its clones. The workspace and individual clones do not get one. A term that only
one clone uses is usually implementation vocabulary the code already states.

## Who changes them

Agents generalize poorly from their own mistakes and bloat context files with ticket-specific
lessons. Do not add to a context file, rule, or skill on your own initiative after a mistake.
Propose the change to the user with the ladder tier it passed, and edit only once they agree.
