# Issue #24 — Linux container install/lifecycle acceptance

**Scope:** isolated x86-64 containers using the local distribution from the issue-24 worktree, mounted read-only at `/src`. These are distro-base container results only: `ubuntu:24.04` (Ubuntu 24.04.5 LTS) and `archlinux:latest` (Arch Linux). This is **not** Omarchy certification or an installed-host certification. No source was pushed, deployed, or published; issue #24 was not closed.

## Images and provenance

Pulled during this run:

- `ubuntu:24.04` — `sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3`
- `archlinux:latest` — `sha256:b21322c663be387c0ed9cbc7bbbfe18e41633ad4e7b7c77cfad45f128be20040`

The bind-mounted local source was the current worktree branch `test/issue-24-linux-lifecycle`, based at `8baa6d3a79449491650a3f00915db8dba8d1bccd`, with the installer repair in this worktree. Both base images started without Hermes, uv, Copilot CLI, or Herdr. Blank tests also began without Python; installer installed distro Python (apt on Ubuntu; pacman on Arch).

## Fresh install checks

Commands run (each in a new disposable container):

```sh
docker run --rm -v "$PWD:/src:ro" ubuntu:24.04 bash -lc 'set -euo pipefail; bash /src/install --workspace /root/workspace --company company --blank=yes --non-interactive; test -f /root/workspace/MANUAL.md; /root/.local/bin/company --help >/tmp/help.out; grep -q add-project /tmp/help.out; test ! -e /root/.hermes; ! command -v copilot; ! command -v herdr; printf "UBUNTU_BLANK_PASS\\n"'

docker run --rm -v "$PWD:/src:ro" archlinux:latest bash -lc 'set -euo pipefail; bash /src/install --workspace /root/workspace --company company --blank=yes --non-interactive; test -f /root/workspace/MANUAL.md; /root/.local/bin/company --help >/tmp/help.out; grep -q add-project /tmp/help.out; test ! -e /root/.hermes; ! command -v copilot; ! command -v herdr; printf "ARCH_BLANK_PASS\\n"'

docker run --rm -v "$PWD:/src:ro" ubuntu:24.04 bash -lc 'set -euo pipefail; export DEBIAN_FRONTEND=noninteractive; bash /src/install --workspace /root/workspace --company company --runtime copilot --non-interactive >/tmp/install.log 2>&1; mkdir -p /root/workspace/payments; /root/.local/bin/company add-project /root/workspace/payments --json; test -d /root/workspace/payments/wiki; /usr/local/bin/copilot --version; /root/.local/bin/herdr --version; test ! -e /root/.hermes; printf "UBUNTU_COPILOT_INSTALLED_CLI_PASS\\n"'

docker run --rm -v "$PWD:/src:ro" archlinux:latest bash -lc 'set -euo pipefail; bash /src/install --workspace /root/workspace --company company --runtime copilot --non-interactive >/tmp/install.log 2>&1; mkdir -p /root/workspace/payments; /root/.local/bin/company add-project /root/workspace/payments --json; test -d /root/workspace/payments/wiki; /usr/local/bin/copilot --version; /root/.local/bin/herdr --version; test ! -e /root/.hermes; printf "ARCH_COPILOT_INSTALLED_CLI_PASS\\n"'
```

Observed outputs:

- Ubuntu blank: `[theSystem] Ready. Runtime: none; workspace: /root/workspace`; `UBUNTU_BLANK_PASS` (exit 0).
- Arch blank: `[theSystem] Ready. Runtime: none; workspace: /root/workspace`; `ARCH_BLANK_PASS` (exit 0).
- Ubuntu `--runtime copilot`: add-project returned `{"command":"add-project","idempotent":false,"project":"/root/workspace/payments","status":"ok"}`; Copilot CLI `1.0.89`; Herdr `0.9.1`; `UBUNTU_COPILOT_INSTALLED_CLI_PASS` (exit 0).
- Arch `--runtime copilot`: same successful project registration; Copilot CLI `1.0.89`; Herdr `0.9.1`; `ARCH_COPILOT_INSTALLED_CLI_PASS` (exit 0).
- For both runtime installs, Hermes home remained absent. This verifies the Hermes-independent Copilot-only route, not the default Hermes install or authenticated agent work.

## Lifecycle and preserved user data

For each distro, a fresh blank install was followed by a user edit to installed `MANUAL.md`, fixtures for a project wiki/raw source, ticket/run JSON, `.thesystem/credentials`, and a source repository; then upgrade, rollback, and uninstall. The checks asserted that upgrade replaces the managed manual edit, rollback restores it, and uninstall preserves that edit plus every data fixture while removing the owned `company` launcher.

```sh
# Run separately with ubuntu:24.04 and archlinux:latest in place of IMAGE
docker run --rm -v "$PWD:/src:ro" IMAGE bash -lc 'set -euo pipefail; bash /src/install --workspace /root/workspace --company company --blank=yes --non-interactive >/tmp/install.log 2>&1; printf "USER_EDIT_MARKER\\n" >> /root/workspace/MANUAL.md; mkdir -p /root/workspace/payments/wiki/raw /root/workspace/payments/tickets/run /root/workspace/.thesystem/credentials /root/workspace/source-repo; printf "company fact\\n" > /root/workspace/payments/wiki/raw/keep.md; printf "ticket record\\n" > /root/workspace/payments/tickets/run/run.json; printf "credential fixture\\n" > /root/workspace/.thesystem/credentials/keep; printf "repo sentinel\\n" > /root/workspace/source-repo/keep; bash /src/install --workspace /root/workspace --company company --upgrade --blank=yes --non-interactive >/tmp/upgrade.log 2>&1; ! grep -q USER_EDIT_MARKER /root/workspace/MANUAL.md; grep -q "Preserving company command" /tmp/upgrade.log; bash /src/install --workspace /root/workspace --rollback >/tmp/rollback.log 2>&1; grep -q USER_EDIT_MARKER /root/workspace/MANUAL.md; for f in payments/wiki/raw/keep.md payments/tickets/run/run.json .thesystem/credentials/keep source-repo/keep; do test -s "/root/workspace/$f"; done; bash /src/install --workspace /root/workspace --company company --uninstall >/tmp/uninstall.log 2>&1; test ! -e /root/.local/bin/company; for f in payments/wiki/raw/keep.md payments/tickets/run/run.json .thesystem/credentials/keep source-repo/keep; do test -s "/root/workspace/$f"; done; test -f /root/workspace/MANUAL.md; printf "LIFECYCLE_DATA_PRESERVED\\n"'
```

Output on Ubuntu: `UBUNTU_UPGRADE_ROLLBACK_UNINSTALL_DATA_PRESERVED` (exit 0). Output on Arch: `ARCH_UPGRADE_ROLLBACK_UNINSTALL_DATA_PRESERVED` (exit 0).

## Defect found and fix

The first Arch lifecycle attempt failed at upgrade after the distribution had been upgraded: `cmp: command not found`, followed by `company command already exists; refusing to overwrite: company`. The launcher's stored path points at the installed workspace, while a local-source upgrade generates a different temporary launcher; comparing the two as if a fresh install should collide was incorrect. The installer now preserves and validates the existing workspace-bound launcher on `--upgrade`, and uses Python byte comparison for normal idempotent launcher checks instead of the undeclared `cmp` utility. Ubuntu and Arch upgrade/rollback/uninstall were both rerun successfully after this repair. No destructive fallback was added.

An initial Ubuntu clean Copilot test also returned exit 1 because the test then incorrectly ran `company --help` without the installed `~/.local/bin` in `PATH`; the installer itself had completed successfully. The corrected probes call the launcher by its installed absolute path and passed. This was a test-harness correction, not a product defect.

## Verification and remaining gaps

- `python3 -m unittest discover -s tests -q`: 63 tests, OK (1 skipped).
- `bash -n install bootstrap` and `git diff --check`: pass.
- Container checks do **not** certify the default Hermes install/setup, human provider sign-in, interactive TTY or desktop behavior, authenticated Copilot model turns, Herdr launch/session interaction, interrupted-install recovery, remote release/archive distribution, actual Omarchy, or host-specific behavior. No authentication was supplied or simulated.
- Lifecycle fixtures are synthetic sentinel files; they demonstrate preservation of these paths and user-edited installed content, not a migration of a real user's credentials or company workspace.
