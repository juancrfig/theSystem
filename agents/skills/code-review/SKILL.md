---
name: code-review
description: Review a branch, pull request, or work in progress since a fixed point against documented standards and an identified specification. Use for code review requests, including "review since X".
---

# Code Review

Review the actual diff in two independent axes:

- **Standards:** documented instructions and conventions applicable to the changed paths.
- **Spec:** whether the diff meets the originating issue, request, or specification.

Keep the axes separate. A standards-compliant change can be the wrong product change, and a correct feature can violate a documented convention.

## 1. Establish a reviewable fixed point

Use the user's supplied commit, branch, tag, merge base, or PR as the fixed point. If none was supplied, ask for one. For a PR URL, first resolve its repository, source revision, target revision, and work-item links; review that pinned source revision against the target merge base.

Review in the repository containing the changed code. Preserve its working tree: use an existing clean checkout or a detached worktree for a PR. Do not treat ignored, untracked, or locally generated tests as PR evidence.

Before substantive review, verify that the fixed point resolves and inspect:

```sh
git diff --check <fixed-point>...HEAD
git diff --find-renames <fixed-point>...HEAD
git log --oneline <fixed-point>..HEAD
```

An empty diff is a valid result, not a reason to invent findings. Record the fixed point and validation limits.

## 2. Locate the specification

Use evidence in this order:

1. Work-item links or issue keys in the PR and commits.
2. A path or specification supplied by the user.
3. A matching local specification in the repository's documented planning locations.

Read the identified source in full. If no authoritative specification can be identified, run a **Standards-only** review. Do not ask the user to invent a spec, and state that the Spec axis was skipped.

## 3. Collect applicable standards

Read, in full, the repository instructions that apply to every changed path: root and nested `AGENTS.md`, `CONTRIBUTING.md`, and documented coding-standard files. Obey their stated precedence. If the workspace uses an `agents/rules/` hierarchy, collect every applicable rule document in this order:

1. Workspace-wide `agents/rules/*.md`.
2. The changed project's `agents/rules/*.md`.

More-specific documented rules override broader rules. Do not invent a third tier or load legacy/sibling rule trees merely because they exist. A documented rule breach is a standards finding; cite the file and rule. If no standards source is found, say so instead of treating personal style as a hard requirement.

Also inspect the change for clearly evidenced maintainability risks (for example duplicated logic, unclear names, data clumps, or unnecessary abstraction). Label these as **judgement calls**, never hard violations, and suppress them where documented conventions endorse the pattern. Do not report items already enforced by a passing formatter, linter, or type checker unless the diff shows that enforcement is absent or bypassed.

## 4. Run the two reviews independently

When delegation is available and the review is substantial, run the Standards and Spec passes in parallel. Otherwise perform them independently yourself. Give each pass the fixed-point commands, changed-file list, and only the evidence for its axis.

The Standards pass must report only findings grounded in an applicable document or clearly labelled judgement calls. The Spec pass must quote the requirement it believes is missing, incorrect, or exceeded. Each finding needs an accurate file and line, impact, and a concise remediation. Do not infer runtime success from static inspection.

For source-code changes, perform an explicit security pass over changed trust boundaries. Trace plausible paths from untrusted input to sensitive operations (for example, secret handling, command or query construction, deserialization, path access, and data egress), reading surrounding code as needed. Report a security concern only when the changed code and its context support a concrete risk and impact; a regex match or suspicious-looking token alone is a lead to investigate, not a finding. Place each substantiated finding on the applicable Standards or Spec axis without merging the axes.

Run relevant project checks when the environment permits. When a check fails, distinguish a regression from a pre-existing failure by running the same check against the fixed-point revision in an isolated checkout or worktree where feasible. Do not stash/pop or otherwise alter the review worktree to establish a baseline. Call a failure new or pre-existing only when the baseline and changed revision were checked under comparable commands and conditions; otherwise mark its origin inconclusive.

If review is followed by an authorized code change, run the repository's documented verification commands before modifying code. Distinguish static review, local test/runtime evidence, browser/device evidence, and live-provider evidence. Report checks that were unavailable, skipped, or failed with the reason and relevant command/result; do not silently treat missing tools or unrun checks as passing.

## 5. Report

Use this structure:

```markdown
## Standards

- [severity] `path:line` — finding, applicable rule or labelled judgement call, impact.

## Spec

- [severity] `path:line` — requirement and gap.

## Validation

- Fixed point: ...
- Static: ...
- Local test/runtime: ...
- Browser/device: ...
- Live/provider: ...
```

Keep Standards and Spec findings separate; do not combine or rerank them. If either axis has no findings, say so and name the evidence reviewed. End with the finding counts by axis and the most severe item within each axis.
