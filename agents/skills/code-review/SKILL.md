---
name: code-review
description: Review a branch, pull request, or work in progress since a fixed point against theSystem's rules and the task it implements. Use for code review requests, including "review since X".
---

# Code Review

Whoever asks for the review provides what to review against: the fixed point, the spec and the rules. This skill says how to review.

Review the diff on two independent axes:

- **Standards:** does the change follow the rules you were given?
- **Spec:** does it do what the task asked, no less and no more?

Keep the axes separate. A change can follow every rule and still build the wrong thing, or do exactly what was asked and break a rule. Reporting them separately stops one axis from hiding the other.

## 1. Pin the fixed point

Use the fixed point you were given: a commit, branch, tag, merge base or PR. If none was given, ask for it. For a PR, review its source revision against the target's merge base in a detached worktree. Never change the working tree you review.

Confirm the fixed point resolves, then capture:

```sh
git diff --check <fixed-point>...HEAD
git diff --find-renames <fixed-point>...HEAD
git log --oneline <fixed-point>..HEAD
```

An empty diff is a valid result: report it and do not invent findings. Ignored, untracked or locally generated files are not part of the change.

## 2. Gather the inputs

**Spec.** The spec is the task text you were given. If there is none and you can ask, ask once. If no spec exists, review Standards only and say that the Spec axis was skipped.

**Rules.** Enforce the theSystem rules you were given. If none were given and you can ask, ask the human which apply; otherwise say that no rules were provided. For each rule, run its `Enforce with:` steps and cite the rule file. A rule marked `experimental: true` is reported as a judgement call, never as a hard finding.

**Other guidelines.** Enforce only rules that theSystem defines. If you find other guideline files, for example a source clone's `AGENTS.md`, `CONTRIBUTING.md`, `CODING_STANDARDS.md` or a style guide, do not apply them. List them in the report so the human can decide.

**Smell baseline.** Also check the diff against these code smells (Fowler, _Refactoring_, ch. 3). Each smell is a judgement call ("possible Feature Envy"), never a hard finding. A theSystem rule that endorses the pattern suppresses the smell. Skip anything that a passing formatter, linter or type checker already enforces. Each smell reads *what it is* → *how to fix*:

- **Mysterious Name**: a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code**: the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy**: a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps**: the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession**: a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches**: the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery**: one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change**: one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality**: abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains**: long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man**: a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest**: a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

## 3. Review

When you can delegate, run the Standards pass and the Spec pass as two parallel sub-agents. A sub-agent sees only its brief, so paste into it, in full, the fixed-point commands, the changed-file list and the evidence for its axis: the rules and the smell baseline for Standards, the task text for Spec. Ask each for a report under 400 words. Without delegation, run the two passes yourself and keep them independent.

- **Standards** findings cite a rule file, or name a smell as a judgement call.
- **Spec** findings quote the requirement and say whether it is missing, wrong, or exceeded (behaviour nobody asked for).
- Every finding gives the file and line, the impact and a short fix. Do not infer runtime success from reading the code.

For source-code changes, also run a security pass over the changed trust boundaries. Trace plausible paths from untrusted input to sensitive operations: secret handling, command or query construction, deserialization, path access and data egress. Report a concern only when the code and its context support a concrete risk; a suspicious-looking token alone is a lead to investigate, not a finding. Put each security finding on the Standards or Spec axis.

Review by reading only. Do not run tests, the application, builds, linters or other checks unless the human explicitly asked for them in the request or the task. Never stash or otherwise alter the reviewed tree.

## 4. Report

```markdown
## Standards

- [hard | judgement] `path:line`: finding; rule file or smell; impact; fix.

## Spec

- [missing | wrong | exceeded] `path:line`: quoted requirement; gap; fix.

## Other guidelines found

- `path`: what it asks. Not applied.

## Fixed point

- ...
```

Only hard findings and Spec findings block the change; judgement calls never block on their own. Do not merge or rerank the two axes. If an axis has no findings, say so and name the evidence you reviewed. End with the finding count per axis and the worst finding within each axis.
