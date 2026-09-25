# 07: Bundle builder

**What to build:** the orchestrator builds each agent's bundle as `AGENTS.md` describes: overlay
the project tier on the global tier, keep only what the agent's roles list, mount it read-only, and
write a manifest (path and hash of every file) into the run record. It refuses to start when the
reviewer's rules do not include every implementer rule.

**Why:** copy per run instead of sharing profile state (analysis 3.4). Rules as the contract is
the one choke point you *want*, so it must be enforced in code, not prose. Today
`orchestrator.yaml` uses a singular `role:` key, its role lists contain empty entries that YAML
reads as `null`, and the `base` role lists two of the four global rules.

**Blocked by:** 06

**Status:** needs-decision

## Decisions

1. **Where project roles live.** Recommended: `<project>/agents/orchestrator.yaml`, overlaid on
   the global one by the same tier rule. Otherwise the global file becomes a choke point that
   every project edits.
2. **How an agent gets its roles.** Recommended: from the ticket (see 04), falling back to the
   `implementer`/`reviewer` role of the same name.
3. **Unknown or empty entries.** Recommended: a hard error, never a silent skip.

- [ ] Each decision above is answered.
- [ ] A project file with the same relative path replaces the global one. A skill is replaced as a
      whole directory.
- [ ] A reviewer role set that lacks one implementer rule is refused, and the refusal names the
      rule.
- [ ] The manifest lists every file with its hash. Two runs with the same inputs produce the same
      manifest.
- [ ] Agents see the bundle read-only, separate from the worktree.
- [ ] Tests use fixture tiers. None of them touch the real `agents/`.
