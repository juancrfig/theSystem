---
name: ticket-system-maintenance
description: Use when creating, reviewing, updating, organizing, or closing a project's tickets. Keep the tracker authoritative and verify every change.
---

# Ticket-system maintenance

The agent working on **theSystem** owns its ticket system end to end. Create, review, update, organize, link, verify, and close tickets; preserve evidence and dependencies; the user is not expected to maintain the tracker.

This skill applies to theSystem's own GitHub repository and Project. It does not silently move a product project to GitHub: follow that project's documented tracker unless the user explicitly authorizes a migration.

## Operating rules

1. Inventory the repository, current tracker issues, labels, Project items, dependencies, and working-tree changes before mutating anything.
2. Separate theSystem work from product-project execution contracts. Never turn a product project's local ticket rules into a claim that every project uses GitHub.
3. Preserve requirements, acceptance criteria, dependencies, evidence, and unresolved decisions. Sanitize client names, personal details, credential locations, private identifiers, and secret values before publication.
4. Treat historical statuses as evidence, not truth. Re-evaluate current state from code, tests, runs, and tracker records; do not mark work complete because an old ticket said so.
5. Create or update one canonical ticket per coherent unit of work. Use labels and Project fields consistently; organize every theSystem ticket in the theSystem Project.
6. Record blockers as explicit tracker links or native dependency relationships. Do not hide dependencies in prose when the tracker supports a relationship.
7. After every external write, read the exact issue, label, Project, relationship, or comment back and compare it with the intended payload. A successful API response is not proof of the desired state.
8. Close a ticket only when its acceptance criteria and completion evidence are verified. Link the evidence and state what was checked. Never infer completion from a commit, label, or optimistic report alone.
9. During migration, map each removed local source to its remote issue URL in an out-of-repository manifest. Remove local ticket artifacts only after all remote records and dependency links have been read back.
10. Perform a criterion-level completeness check: compare every source acceptance criterion, design decision, dependency, risk, and open decision with the remote body or comment, and record the target and verification evidence for each; summaries are not sufficient.
11. Keep migration and publication audits explicit. Do not rewrite git history or push unless separately authorized.

## Create or review a ticket

- Gather the full source context and search the repository for an existing implementation or duplicate ticket.
- Write a title that names the durable outcome, not the source filename.
- Include scope, acceptance criteria, dependencies, evidence expectations, open decisions, and a sanitized migration/source note when applicable.
- Apply exactly one category label and one workflow-state label unless project policy says otherwise. Use `needs-triage` when current readiness is not verified.
- Add the issue to the correct Project and verify its item, fields, and URL.
- For a review, read the entire issue, comments, linked work, labels, Project fields, and current code evidence before recommending a state.

## Update, organize, and close

- State the exact target and intended mutation before performing it.
- Update the issue body when requirements or evidence change; do not erase unresolved history.
- Keep title, labels, Project status, dependency links, and evidence mutually consistent.
- Use `ready-for-agent` only when scope, acceptance criteria, dependencies, and prerequisites are actually verified. Use `ready-for-human` when judgment or external action remains.
- Close only after read-back confirms the final body, labels, Project organization, and completion evidence. If verification is blocked, leave the ticket open and report the blocker.

## Migration checklist

- Inventory every local ticket, spec, issue, rendered derivative, and reference.
- Classify stale status claims, sensitive details, and dependencies.
- Create remote tickets in dependency order, then add reciprocal links or native relationships.
- Read back every issue and Project item; save a source-to-remote manifest outside the repository.
- Re-scan the repository and remote issue bodies for removed sensitive or local-only material.
- Delete local ticket artifacts only after the manifest and read-back checks succeed.
- Report exact issue IDs, URLs, Project URL, manifest path, scans, tests, and any remaining blockers.
