---
name: tdd
description: Test-driven development. Use when building a feature or fixing a bug test-first, when the user mentions "TDD" or "red-green-refactor", or wants integration tests.
---

Sources: [mattpocock/skills](https://github.com/mattpocock/skills) v1.3.1 `tdd` (MIT), merged with Hermes Agent's `test-driven-development`, adapted from [obra/superpowers](https://github.com/obra/superpowers) (MIT).

# Test-Driven Development

TDD is the red → green loop: write a failing test, watch it fail, write the least code that makes it pass, watch it pass. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle: consult them before and during the loop, not after.

**Why the order matters:** a test you never saw fail proves nothing. It may test the wrong thing, test the implementation instead of the behavior, or pass by construction. Tests written after the code answer "what does this do?"; tests written first answer "what should this do?".

When exploring the codebase, read the project's `GLOSSARY-MAP.md` and follow the relevant context links, or read its root `GLOSSARY.md` if there is no map, so test names and interface vocabulary match the domain language. Respect ADRs in the area you're touching.

In an unattended run (no one answers questions), wherever this skill says ask or confirm with the user, stop and put the question in your handoff instead.

## When it applies

Every new behavior and every bug fix. For a bug, first find the cause with `debug`; its regression test is the red step here.

Not for throwaway prototypes (use `spike`), generated code, or pure configuration. Skipping TDD for anything else needs the user's or the task's explicit permission; "too simple to test" is not one.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification: "user can checkout with valid cart" tells you exactly what capability exists, and it survives refactors because it doesn't care about internal structure.

- One behavior per test. An "and" in the name means split it.
- The name says what the caller gets, not how the code does it.
- Real code, not mocks. Mock only at system boundaries.
- Cover the edge cases and error paths the behavior promises, not only the happy path.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams: where tests go

A **seam** is where a module's interface lives. Tests cross it exactly as callers do, never reaching inside.

**Test only at agreed seams.** You can't test everything, so agreeing the seams up front is how testing effort lands on the critical paths and complex logic instead of every edge case. Use the seams the task gives. If none are given:

- In a chat, write down the seams you propose and confirm them with the user before writing any test: "What's the public interface, and which seams should we test?"
- In an unattended run, test at the module's public interface and list the seams you chose in your handoff, so the reviewer checks them.

When the shape of that interface is itself in question (how deep the module is, where the seam belongs, what the interface should expose), load `codebase-design` for the vocabulary. It is the shared source of the module, interface, depth, seam, adapter, leverage and locality terms, and it is a reference to consult, not a session to run.

## The loop

Use the test command the task or the user gave you. If none was given, use the one the project documents, and say which one you used.

1. **Red: write one failing test** for the next behavior at an agreed seam.
2. **Watch it fail.** Never skip this. Run that one test and check that it fails because the behavior is missing: not a typo, an import error or a broken fixture. A test that passes at once is testing behavior that already exists, or nothing; fix the test. A test that errors is not red yet; fix the error and run it again.
3. **Green: write only enough code to pass it.** No anticipated features, no options nobody asked for, no clean-up of unrelated code.
4. **Watch it pass**, then run the whole suite. If the new test fails, fix the code, not the test. If another test broke, fix that now. The output must be clean: no new errors or warnings.
5. **Repeat** with the next behavior.

**Code written before its test** (yours or found in the working tree) is not covered until you have seen a test fail without it. Set the change aside (stash it or comment it out), watch the test go red, restore it, and watch the test go green. If the test stays green with the code removed, the test is wrong.

## Anti-patterns

- **Implementation-coupled**: mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological**: the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth: a known-good literal, a worked example, the spec.
- **Horizontal slicing**: writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead: one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Refactoring is not part of the loop.** Don't restructure code between cycles; finish the slices first.

## Tidy pass before you hand off

When every slice is green, make one tidy pass over the code this task added or changed: remove duplication, improve names, extract a helper where it makes the code clearer, simplify expressions. Rules:

- Only code from this task. Don't touch other files or code you didn't change.
- No new behavior. If a change would need a new test, it isn't tidying.
- Run the whole suite after the pass. If anything goes red, undo the last change and take a smaller step.

Larger restructuring (moving modules, changing interfaces) is a finding for the review, not part of this pass.

## When the test is hard to write

A hard test is a design signal. Listen to it before forcing the test through.

- **You don't know how to test it:** write the call you wish existed, then the assertion, then make them real.
- **The test needs a huge setup:** the interface asks too much of its callers. Simplify it, or load `codebase-design`.
- **You must mock everything:** the code is too coupled. Pass the dependencies in, and mock only the system boundaries.

## Red flags

Stop and go back to red when you notice any of these:

- Production code that no failing test asked for.
- A new test that passed on its first run.
- You can't say why the test failed.
- "I'll add the tests after", "I already tested it by hand", "it's too simple to test", "just this once".

## Before you report done

- [ ] Every new behavior has a test, at an agreed seam.
- [ ] You saw each test fail for the expected reason before its code existed.
- [ ] The whole suite passes, and the output has no new errors or warnings.
- [ ] Mocks appear only at system boundaries.
- [ ] The tidy pass is done and the suite is still green.
