# 01: Workspace check gate

**What to build:** one command, `./check`, that runs every deterministic check the workspace has,
and a pre-commit hook that calls it. A commit is refused when any check fails. The checks are:

- every rule has its three fields (the existing hook, moved under `./check`);
- every path that an `AGENTS.md`, `CONTEXT.md`, skill, or `orchestrator.yaml` points to exists;
- all test suites pass, found by one discovery command instead of two locations with two
  runners;
- no secret or company-identifying string is staged, using a pattern list plus a denylist of
  organization names, client names, internal hosts and emails kept in an ignored local file.

Land it green: every pointer that is dangling today is either created or removed, as the human
decides.

**Why:** when docs are input to agents, a broken pointer is a bug. Keeping copies in sync is only
cheap when a machine checks (analysis 3.3, 3.5). Today `AGENTS.md` points at three paths that do
not exist, and agents rediscovered this in at least four sessions. The company-data cleanup before
publishing was a one-time manual pass.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `./check` exits non-zero and names the file and the reference for each failure.
- [ ] The pre-commit hook runs `./check` against the staged content, not the working tree.
- [ ] Adding a new rule, skill, or test file needs no edit to `./check`: it discovers them
      (rule `bootstrap-reconciles-canonical-declarations`).
- [ ] A fixture with a dangling pointer fails. A fixture with a planted fake key fails. A fixture
      with a denylisted company name fails.
- [ ] The denylist lives in an ignored file, with a committed example, so the check does not
      publish the names it protects.
- [ ] The scan's scope is decided and stated. `.scratch/` is committed, and this analysis names
      client projects on purpose. Recommended: scan `agents/`, the root files, and tests; skip
      `.scratch/`, since this private repo keeps working material there.
- [ ] The current dangling pointers (`wiki/index.md`, `wiki/practices/knowledge-system.md`,
      `agents/utils/`) are resolved, and `./check` passes on master.
