# Developing theSystem

`FEATURES.md` is the human-owned feature map and the only definition of what theSystem does. Edit it only with the
human's explicit approval of the change.
Anything not in the map is not wanted, and items under "Later" must not be built yet. Every change names the
feature ID it serves.

This is the `no-tests-main-orchestrator` branch (ADR 0004): the main agent orchestrates tasks with subagents, and
there is no orchestrator program and no test suite.

```text
FEATURES.md   the feature map
install       the installer (F1); installs the newest commit of this branch, or this working tree with --dev
thesystem/    the workspace command (`update`), installer helpers and the artifact library (F1, F7, F9, F10)
workspace/    files seeded into a new workspace (AGENTS.md is the main agent's guide)
agents/       roles, rules and skills seeded into a new workspace's agents/
docs/adr/     decisions
.github/      release notes configuration (release.yml)
```

Tests are a scarce good: write them only at the end of development and only with the owner's explicit approval.
Do not verify changes (run, build, lint) unless the owner asks. Follow
`agents/rules/tests-and-verification-need-human-approval.md`.

GitHub Issues is the tracker for theSystem's own development: https://github.com/juancrfig/theSystem/issues.
Do not create or switch git branches unless the user asks. Development on this variant pushes straight to the
`no-tests-main-orchestrator` branch; only proposals from workspaces (F10) use pull requests.

## Releases (F10)

This branch has no numbered releases. Every commit pushed to `no-tests-main-orchestrator` is its newest release:
workspaces installed from it pick it up on their next `update`. Write clear commit messages; they are the release
notes.
