---
name: debug
description: Root-cause debugging loop for bugs, failing tests and performance regressions. Use when the user says "diagnose" or "debug this", or reports something broken, throwing, failing or slow.
---

Sources: [mattpocock/skills](https://github.com/mattpocock/skills) v1.3.1 `diagnosing-bugs` (MIT), merged with Hermes Agent's `systematic-debugging`, adapted from [obra/superpowers](https://github.com/obra/superpowers) (MIT).

# Debug

A discipline for bugs: find the root cause before you change any code. A fix for a symptom you don't understand hides the bug or creates a new one. Skip phases only when explicitly justified, and say which phase you skipped and why.

Use it for every kind of fault: test failures, production bugs, build failures, integration problems, slow code. Use it most when the cause looks obvious, when time is short, or when a fix already failed: those are the moments when guessing is most tempting.

When exploring the codebase, read the project's `GLOSSARY-MAP.md` and follow the relevant context links, or read its root `GLOSSARY.md` if there is no map, to understand the domain vocabulary. Check ADRs in the area you're touching; explore code for the module structure.

When you can delegate, give the exploration in Phases 1–4 to a sub-agent: paste the symptom, the full error and the loop command into its brief, tell it to report findings and change nothing, and cap the answer at 400 words. Otherwise do the work yourself.

In an unattended run (no one answers questions), wherever this skill says ask or confirm with the user, stop and put the question in your handoff instead.

## Redact

This skill has you show commands, outputs and captured artifacts. **Redact every secret first**: write `<REDACTED>` in its place. Build loops against env vars, so the credential stays in the environment rather than in what you show. Captured artifacts carry auth headers: quote only the lines that carry the signal.

If the redacted output is not enough to diagnose the bug, say so and ask the user.

## Phase 1: Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug (one that goes red on _this_ bug), you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

### Start from the evidence you already have

- **Read the error completely.** The whole message, the whole stack trace, every warning before it. Note the file, line and error code. The answer is often in it.
- **Check what changed.** Recent commits, the uncommitted diff, new dependencies, config changes. A bug that appeared after a known change points at that change and makes a bisection loop cheap.

### Ways to construct one, in roughly this order

1. **Failing test** at whatever seam reaches the bug: unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) that drives the UI and asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL bash script.** Last resort. If a human must click, drive _them_ with `scripts/hitl-loop.template.sh` so the loop is still structured. Captured output feeds back to you.

Build the right feedback loop, and the bug is 90% fixed.

### Tighten the loop

Treat the loop as a product. Once you have _a_ loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second deterministic one is tight, a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not, so keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a redacted captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation. Do **not** proceed to hypothesise without a loop.

### Completion criterion: a tight loop that goes red

Phase 1 is done when the loop is **tight** and **red-capable**: you can name **one command** (a script path, a test invocation, a curl) that you have **already run at least once** (show the invocation and its output, redacted), and that is:

- [ ] **Red-capable**: it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring"; it must be able to _catch this specific bug_.
- [ ] **Deterministic**: same verdict every run (flaky bugs: a pinned, high reproduction rate, per above).
- [ ] **Fast**: seconds, not minutes.
- [ ] **Agent-runnable**: you can run it unattended; a human in the loop only via `scripts/hitl-loop.template.sh`.

If you catch yourself reading code to build a theory before this command exists, **stop: jumping straight to a hypothesis is the exact failure this skill prevents.** No red-capable command, no Phase 2.

## Phase 2: Reproduce + minimise

Run the loop. Watch it go red as the bug appears.

Confirm:

- [ ] The loop produces the failure mode the **user** described, not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut, and keep only what's load-bearing for the failure.

Why bother: a minimal repro shrinks the hypothesis space in Phase 3 (fewer moving parts left to suspect) and becomes the clean regression test in Phase 5.

Done when **every remaining element is load-bearing**: removing any one of them makes the loop go green.

Do not proceed until you have reproduced **and** minimised.

## Phase 3: Locate and hypothesise

### Narrow down where it breaks

- **Several components** (API → service → database, CI → build → deploy): run the loop once with a probe at each boundary: what goes in, what comes out, which config and environment arrive. The evidence shows which component breaks; investigate only that one.
- **Error deep in the call stack:** trace the bad value upstream. Who called this with it, and who gave it to them? Keep going until you reach where it was first wrong. Fix there, not where it surfaced.
- **Compare with code that works.** Find similar code in the same codebase that behaves correctly. List every difference between the two, however small; don't assume "that can't matter". If the broken code follows a pattern or a library example, read the reference completely before you judge it.

### Rank hypotheses

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea. Rank them by likelihood and by how cheap they are to falsify.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe: discard or sharpen it.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly ("we just deployed a change to #3"), or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it; proceed with your ranking if the user is AFK.

If every hypothesis is falsified and you don't know what else it could be, say "I don't understand X". Gather more evidence or ask; don't guess.

## Phase 4: Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.** If the probe falsifies the hypothesis, undo it and move to the next one; don't stack changes.

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs. For Python load `python-debugpy`; for Node.js load `node-inspect-debugger`.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single grep. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

## Phase 5: Fix + regression test

Write the regression test **before the fix**, but only if there is a **correct seam** for it. Load `tdd` for what makes the test worth keeping.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. If the only available seam is too shallow (single-caller test when the bug needs multiple callers, unit test that can't replicate the chain that triggered the bug), a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it. The codebase architecture is preventing the bug from being locked down. Flag this for the next phase.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix: **one change**, at the root cause. No "while I'm here" improvements, no bundled refactoring.
4. Watch it pass, then run the whole suite.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.

### When the fix doesn't work

Undo it. Don't add a second fix on top. Go back to Phase 3 with what the failure taught you.

**After three failed fixes, stop fixing.** When each fix reveals a new problem in a different place, the design itself is the likely cause, not one more wrong hypothesis. Report the three attempts and what each one showed, and ask the user whether to keep fixing or rethink the design. Don't try a fourth fix without that answer.

## Phase 6: Cleanup

Required before declaring done:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] The whole suite passes
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The hypothesis that turned out correct is stated in the commit / PR message, so the next debugger learns

## Red flags

Stop and go back to Phase 1 when you catch yourself thinking:

- "Quick fix for now, investigate later." / "Just try X and see."
- "It's probably X, let me fix that." / "I see the problem."
- "I don't fully understand, but this might work."
- "I'll change several things and run the tests."
- "I'll skip the test and check it by hand."
- "One more fix" after two have already failed.
