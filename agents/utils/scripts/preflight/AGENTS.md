# Preflight

Preflight proves that the developer tools are ready to build and test a clone headlessly.

## Create or repair a clone entry point

1. Read the clone's instructions, toolchain pins, lockfiles, CI configuration, and existing
   environment checks. Check the environment that actually runs its tools, including containers.
2. Select a stack template: [React](../../templates/preflight/react/preflight) or
   [Flutter](../../templates/preflight/flutter/preflight). Copy it to the clone root as
   executable `preflight`, then adapt it. These are incomplete starting points; replace their
   explicit failure with the clone's remaining readiness checks. For an unsupported stack, follow
   this contract.
3. Read requirements from the clone's existing authoritative files. Do not copy version numbers
   into the script, infer exact pins from version ranges, or alter requirements to obtain green.
   Missing or conflicting requirements are errors to resolve with the owner.
4. Check all tools needed by the clone's existing build and test routes: SDKs, runtimes, package
   managers, installed locked dependencies, and applicable headless browser/emulator binaries,
   system libraries, or device capabilities. Use bounded version/capability probes, not builds or
   tests. Reuse an existing doctor only if its behavior fits this scope. Do not introduce test
   frameworks or require every possible test level.
5. Use the shared checks for common requirements; do not copy their implementations into stack
   scripts. Exit zero only if every required check passes. Missing tools, incomplete checks, and
   unavailable evidence must not become a pass.
6. `finish_preflight` also validates the Hermes Agent skill harness. `agents/skills/` is the
   only canonical source. It creates or repairs a relative link for every valid canonical skill
   in `.agents/skills/`. Do not duplicate skills in a second harness, and do not retain
   `agents/openai.yaml` UI metadata in canonical skills. A real non-symlink at a required
   harness path is a failure that needs owner action.
7. On failure, print the requirement source, observed problem, and targeted recovery action.
   Fix the environment and rerun. Change a check only when the check is wrong. The script checks;
   the agent performs repairs.

## Optional credentials

Keep credentials outside the repository. A clone may add a read-only identity check only when an
existing build or test route requires that provider. Read a gitignored `.env` as data, never by
sourcing it. Do not require organization-specific providers or credentials in the shared checker.

## Verify changes to shared checks

Run the shared preflight test suite from the workspace root:

```bash
python3 -m unittest discover agents/utils/scripts/preflight/tests
```
