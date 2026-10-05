---
name: propose-default
description: "Use when offering a workspace improvement back to theSystem as a new default (a proposal). Lists candidate files, checks them for company information, and opens one labeled pull request per improvement after the human says yes."
---

# Propose a default

A proposal is a pull request from this workspace that offers a local improvement as a new theSystem default. Once
it is merged and released, the company command's `update` brings every server in line.

You can propose at any time, inside or outside a memory review. The human is the only gate: open nothing without
their explicit yes.

## What can be proposed

Only theSystem's own files: the ones the installer seeded (workspace `AGENTS.md`, `GLOSSARY.md` and everything in
global `agents/`), plus new files in global `agents/`. Never propose project folders, `.thesystem/`, Hermes memory
or personal skills. Hermes settings changed by hand do not travel; only edits to the files in `agents/.harness/` do.

## Steps

1. **List the candidates.** From the workspace, run:

   ```bash
   python3 agents/skills/propose-default/scripts/candidates.py list
   ```

   Each candidate is `changed`, `added` or `deleted` compared with the baseline (the release this workspace was
   installed or last updated from), with its path in theSystem (`repo_path`). Read the diff of each one against
   `.thesystem/baseline/files/<path>`.
2. **Group them into improvements.** One improvement is one pull request: the files that change together for one
   reason. Leave out changes the human does not want to share.
3. **Write what and why.** For each improvement, write a short description: what changes, and the incident or
   lesson behind it, so the owner can judge it without this conversation.
4. **Check for company information.** Read every line the proposal adds. Flag client, project and people names,
   internal URLs and hostnames, ticket ids, credentials and secrets. Show the human each flagged line and the
   rewrite you suggest. The company command's name is replaced by `{{COMMAND}}` automatically in `AGENTS.md`;
   flag it anywhere else.
5. **Ask.** Show the human the improvement: title, label, files, description and check result. Open the pull
   request only after they say yes. A change to the proposal means asking again.
6. **Open the pull request** in a temporary worktree of `~/theSystem`, so the clone's checkout is never disturbed:

   ```bash
   clone=~/theSystem
   branch=propose/<short-name>
   tree=$(mktemp -d)/theSystem
   git -C "$clone" fetch --quiet origin master
   git -C "$clone" worktree add --quiet -b "$branch" "$tree" origin/master
   python3 agents/skills/propose-default/scripts/candidates.py apply --repo "$tree" <path>...
   git -C "$tree" add -A
   git -C "$tree" commit --quiet -m "<title>"
   git -C "$tree" push --quiet -u origin "$branch"
   gh pr create --repo juancrfig/theSystem --head "$branch" --base master \
     --title "<title>" --body "<what and why>" --label <label>
   git -C "$clone" worktree remove --force "$tree"
   ```

   `apply` carries each workspace edit onto `master` at its theSystem path and reverses install substitutions.
   When it reports `"conflict": true`, resolve the markers in that file first. Check `git -C "$tree" diff --cached`
   before committing: it must hold only this improvement.
7. **Report** the pull request link. Proposals that touch the same file can conflict; mention it when they do.

## Labels

Pick one, so the release notes are grouped:

- `skills`: a skill added or improved.
- `rules`: a rule added or improved.
- `roles`: `roles.yaml` changes.
- `wizard`: the installer, the workspace guide, the glossary or the harness files.
- `orchestrator`: the orchestrator and the company command.
- `fix`: something that was broken.
