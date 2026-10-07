# ADR 0003: Releases, a recorded baseline and three-way updates of workspace files

- **Status:** Accepted
- **Date:** 2026-10-05
- **Feature:** F10 (refines ADR 0002)

## Context

ADR 0002 made the installer seed missing files and never overwrite existing ones. That keeps the human's files
safe, but an improvement merged into theSystem then never reaches an existing workspace, and a workspace cannot
tell its own edits apart from outdated theSystem files.

## Decision

1. Servers install and update only to numbered releases (`vMAJOR.MINOR` tags; existing three-part tags remain valid), read from the server's one
   clone (`~/theSystem`) with `git archive`, so the clone's checkout is never touched. `install --dev` installs a
   working tree for development and tests.
2. A workspace records its baseline in `.thesystem/baseline/`: the release tag and a copy of the files it shipped,
   after substitutions. The installer records it only when the workspace holds exactly that release; anything
   else is adopted by the first update.
3. `update` runs the new release's own installer with `--update` (silent steps, new program), then the new
   program merges each file with `git merge-file` (baseline, workspace, release). Conflicts keep standard markers;
   when one side is missing, the file shows both versions whole between markers, so every conflict is resolved
   the same way: remove the markers (or delete the file).
4. With conflicts, the release's files wait in `.thesystem/pending/`; they become the baseline once no conflict
   file holds markers. The state folder ignores itself (`.thesystem/.gitignore`), so the workspace's own
   `.gitignore` is never edited.

ADR 0002 still holds for installs: they only add missing files. Existing files change only through `update`.

## Rejected alternatives

- **Checking out the release in the clone:** disturbs development in `~/theSystem`.
- **Overwriting unchanged files only, without a merge:** loses theSystem changes to any file the human touched.
- **Recording the baseline right after a conflicting update:** an unresolved conflict would later look like a
  local edit and be proposed back.
