# Developing theSystem

`FEATURES.md` is the human-owned feature map and the only definition of what theSystem does. Edit it only with the
human's explicit approval of the change.
Anything not in the map is not wanted, and items under "Later" must not be built yet. Every change names the
feature ID it serves; every test proves a feature's `Proof` line.

```text
FEATURES.md   the feature map
install       the installer (F1); installs the latest release, or this working tree with --dev
thesystem/    the workspace command, orchestrator and updates (F4, F6, F7, F10)
workspace/    files seeded into a new workspace (AGENTS.md is the main agent's guide)
agents/       roles, rules and skills seeded into a new workspace's agents/
tests/        one test module per feature
docs/adr/     decisions
.github/      release notes configuration (release.yml)
```

Run the tests with `python3 -m unittest discover -s tests`.

GitHub Issues is the tracker for theSystem's own development: https://github.com/juancrfig/theSystem/issues.
Do not create or switch git branches unless the user asks. Development pushes straight to `master`; only proposals
from workspaces (F10) use pull requests.

## Releases (F10)

Servers install and update only to releases, so `master` can hold unfinished work. When the owner asks for a release:

1. Find the last release and what changed since: `gh release list --limit 1`, then the merged pull requests and
   commits since that tag (`git log --oneline <tag>..origin/master`).
2. Propose the next number, `vMAJOR.MINOR.PATCH`:
   - PATCH: fixes and small skill or rule improvements.
   - MINOR: new features or new skills.
   - MAJOR: changes that break existing workspaces.
3. Show the owner the number and a preview of the notes. GitHub writes them from the merged pull requests, grouped
   by label (`.github/release.yml`): `skills`, `rules`, `roles`, `wizard`, `orchestrator`, `fix`.
4. Only after the owner confirms, publish from `master`:

   ```bash
   gh release create vX.Y.Z --target master --title vX.Y.Z --generate-notes
   ```

5. Tell the owner to run `<company> update` on each server (or ask its main agent to update theSystem).

Never publish a release without the owner's confirmation. Servers may already have updated to a tag: fix a bad
release with a new one, never by moving its tag.
