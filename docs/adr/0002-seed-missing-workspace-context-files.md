# ADR 0002: Seed missing workspace context files without overwriting existing content

- **Status:** Accepted
- **Date:** 2026-10-01

## Context

When configuring or bootstrapping `theSystem` in an existing company workspace, the workspace already possesses its own Git repository, project hierarchy, source code, and custom rules. However, AI agents operating within `theSystem` rely on foundational workspace context files defined by `AGENTS.md`—most notably `GLOSSARY.md` for shared workspace terminology (`Role`, `Worker`, `Ticket`, `Task`).

If an existing workspace is configured without `GLOSSARY.md`, agents operating in the workspace lack authoritative definitions for these core operational concepts. Conversely, performing a blanket distribution copy into an existing workspace introduces two major hazards:
1. It risks clobbering existing human-authored workspace files (e.g., a company's custom `AGENTS.md` or domain documents).
2. It litters the company workspace root with `theSystem`'s own internal implementation code (`thesystem/` package, `bin/`, `the_system_orchestrator.py`).

## Decision

Adopt the principle: **"Seed missing context files only, never overwrite existing."**

1. **Centralized System Binaries and Code:**
   The implementation code for `theSystem` resides centrally under `~/.local/share/thesystem`, and public entry points/aliases reside on PATH under `~/.local/bin/` (`thesystem` and company aliases). System implementation packages are not duplicated into the user workspace root.

2. **Selective Context Seeding:**
   During workspace installation and configuration:
   - Essential workspace-level context files (such as canonical `GLOSSARY.md`) are inspected.
   - If an essential context file does not exist in the workspace, `theSystem` seeds it from canonical templates so agents have full operational vocabulary.
   - If the file already exists (or contains user-defined modifications), `theSystem` strictly preserves it and never overwrites it.

## Rejected alternatives

- **Blanket distribution copy into existing workspaces:** Rejected because copying internal distribution trees pollutes company repositories, creates unneeded files, and complicates git status in customer codebases.
- **Pure wiring with zero context file creation:** Rejected because workspaces missing baseline context contracts leave agents without necessary system terminology.
- **Forced replacement or adoption of existing files:** Rejected because workspace ownership belongs to the human and the company; installer mutations must fail closed rather than clobber user content.

## Consequences

- Existing company workspaces remain clean, containing only their own code, projects, and needed workspace context files.
- Setup is fully idempotent and safe to run on existing codebases.
- Agents working in newly bootstrapped or existing workspaces are guaranteed to find required context files like `GLOSSARY.md`.
