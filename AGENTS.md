# Developing theSystem

`FEATURES.md` is the human-owned feature map and the only definition of what theSystem does. Do not edit it.
Anything not in the map is not wanted, and items under "Later" must not be built yet. Every change names the
feature ID it serves; every test proves a feature's `Proof` line.

```text
FEATURES.md   the feature map
install       the installer (F1)
thesystem/    the workspace command and orchestrator (F4, F6, F7)
workspace/    files seeded into a new workspace (AGENTS.md is the main agent's guide)
agents/       roles, rules and skills seeded into a new workspace's agents/
tests/        one test module per feature
docs/adr/     decisions
```

Run the tests with `python3 -m unittest discover -s tests`.

GitHub Issues is the tracker for theSystem's own development: https://github.com/juancrfig/theSystem/issues.
Do not create or switch git branches unless the user asks.
