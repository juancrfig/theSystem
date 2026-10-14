---
name: to-spec
description: "Turn the current conversation into a specification: no interview, just synthesis of what you've already discussed."
disable-model-invocation: true
---

This skill takes the current conversation context and codebase understanding and produces a spec. Do NOT interview the user; just synthesize what you already know.

Write the spec to `<project>/tickets/<ticket>/spec.md`. Writing it does not authorize execution: the human approves the work when they confirm the task split.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

   Read [Workspace ticket layout](../to-tasks/references/ticket-layout.md) before creating or changing ticket files.

2. Reconcile binding decisions before dispatch: replace superseded decisions in place, then align scenarios and
   screen inventory with the current decisions. Apply approved steering to binding acceptance in place rather than
   leaving conflicting instructions for workers to resolve. Keep superseded wording only when explicitly marked
   historical and non-binding.

   Write the spec using the template below. Include no test plan and no verification steps: tests come only at the
   end of the ticket, with the human's explicit approval. Scenarios are not a test plan: they state observable
   behaviour, not how to check it.

3. Write the approval page `approval.md` next to the spec. Read [Spec approval template](references/approval-template.md)
   first. Delegate the scenarios to a subagent that did not write the spec: pass it only the spec path and the
   template. It writes every scenario into the spec's Scenarios section, and returns the key ones in full, the rest as
   titles, and every point where the spec forced it to guess. Turn each guess into an Open question. You write
   Outcome, Decisions, Not doing and Open.

4. Load `to-tasks` and continue straight into proposing the task split. Show the approval page in chat (not the full
   spec) with the split, so the human reviews both at once. The full spec stays for agents; link it only. If they
   correct anything, update the spec and the approval page, and redo the split.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Out of Scope

A description of the things that are out of scope for this spec.

## Scenarios

Every observable behaviour, written by the scenario subagent (see step 3): id, title, Given / When / Then. Key
scenarios first (also shown in full on the approval page), then the rest. Evidence runs prove these; approved tests
later cover them.

## Further Notes

Any further notes about the feature.

</spec-template>
