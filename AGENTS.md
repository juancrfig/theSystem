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

Servers install and update only to releases. For theSystem, an owner's request to push also authorizes publishing a release; do not ask for another confirmation. An explicit request to push without releasing overrides this default.

1. Find the last release and what changed since: `gh release list --limit 1`, then the merged pull requests and
   commits since that tag (`git log --oneline <tag>..origin/master`).
2. Use two-part versions, `vMAJOR.MINOR`. Increment MINOR for each release; increment MAJOR and reset MINOR to zero for breaking changes. Keep existing three-part tags unchanged.
3. Write concise notes covering every change since the last release, including direct commits and approved planning records. Do not describe planned functionality as implemented.
4. Run the repository checks, commit the requested changes, push `master`, and publish its exact verified commit:

   ```bash
   gh release create vX.Y --target <verified-commit> --title vX.Y --notes-file <notes-file> --latest
   ```

5. Verify the remote commit, release tag, and published release. Report the release link. Publication does not automatically install or update a workspace.

Servers may already have updated to a tag: fix a bad release with a new one, never by moving its tag.
