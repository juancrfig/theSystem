---
name: retro
description: "Conduct a retrospective on a coding session or a task run."
disable-model-invocation: true
---

Sources: [mattpocock/skills](https://github.com/mattpocock/skills) v1.3.1 `retro` (MIT), adapted to theSystem.

The human has asked for a **retrospective**. You suggest changes to the agents' **environment** (rules, skills, roles, task text, context files, checks) so future runs go better. You propose; the human decides. Change nothing until they approve each item.

## Steps

1. Load `writing-docs`. Every candidate you propose is judged by it: whether it earns a line, where it belongs, how it is worded.

2. Read the evidence for what the human names. If they name nothing, use the current session.
   - **A task run by the main agent**: its run folders (`<task>/runs/<run-id>/`). Start with `review.md` and `worker.diff`; open `worker.md` and `run.json` only while the cause is still unknown.
   - **A chat session**: the session transcript.

   When you can delegate, have a sub-agent read the transcripts: give it the question and the files, ask for the moments that went wrong with quotes, capped at 400 words. Otherwise read them yourself.

3. Find candidates in these categories. Each candidate cites the evidence (file and quote) that shows the problem.

   - **Automated checks**: could a linter, type check, hook or CI job have caught the mistake? (Tests follow `../../rules/tests-and-verification-need-human-approval.md`.) Look for the clone's existing check commands first: an existing check that is unwired or broken is the finding, not a new one. A clone with no guardrail at all (no hook and no CI running its checks) is itself a finding. A check is a change to the company's code, so it is a proposal like any other. _Use when_ the agent made a mistake a tool could detect.
   - **Rules**: should a rule be added, clarified or removed? Classify the mistake first. A **mechanical** one (a banned API, an import shape, a file location, a format) gets an automated check, not a rule. A **judgement call** gets a rule in `agents/rules/` (global) or `<project>/agents/rules/`, in the format of `agents/rules/AGENTS.md`, and the role that should follow it lists it. Workers and reviewers both receive the role's rules. _Use when_ the worker made the mistake or the reviewer missed it.
   - **Task text**: the worker sees only `task.md`. Was an agreed seam, check command, constraint or decision missing from it? The fix belongs in `to-tasks` or `to-spec`. _Use when_ the worker guessed at something the human had already decided.
   - **Skills and roles**: did a skill step mislead, stall on a question nobody could answer, or not reach the agent that needed it? _Use when_ the agent followed a skill and still went wrong.
   - **Context files**: should a line in an `AGENTS.md` move to a rule, skill or check, or be cut? _Use when_ a context file is large or carries instructions only some tasks need.
   - **Tool economy**: did the agent make expensive tool calls that could be cheaper? _Use when_ a call was slow or flooded the context.
   - **No-ops**: instructions that do not change behaviour. _Use when_ a steering file is large.
   - **Information access**: what did the agent need and could not see (dev server logs, read-only access to a service)? _Use when_ a crucial fact was missing.

   Guideline files theSystem did not write (a clone's own `AGENTS.md`, `CONTRIBUTING.md`, style guides) are the company's. List what you would change in them; edit them only with the human's explicit approval.

4. Present the candidates to the human in order of severity: the evidence, the proposed change and where it goes. After approval, make the change. If it improves a theSystem default (a global skill, rule or role), offer it back with `propose-default`.
