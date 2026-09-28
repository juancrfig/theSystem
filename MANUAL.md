# theSystem · User manual

Build software with AI agents. Keep control of the requirements, permissions, and result.

> [!IMPORTANT]
> **Human-owned contract · draft awaiting review.** This manual is the highest authority for intended functionality: what the human wants and what AI must build. Publication does not mean every expectation is approved or implemented.

[Get started](#get-started) · [Projects](#register-a-project) · [Workflow](#from-request-to-completed-change) · [Status](#understand-status) · [Permissions](#set-agent-permissions) · [Learning](#review-evidence-and-learning) · [Open decisions](#open-decisions)

## What works today

| Capability | Availability |
| --- | --- |
| Installation, company command, project registration | Implemented |
| Shared planning skills and assisted memory/skill review | Implemented; profile mismatch remains below |
| Experimental rules and skills | Opt-in with `--experimental` |
| Automated task admission, isolated execution, independent review, run records | **Designed only** |

“Implemented” describes repository capability, not a fresh deployment certification.

> [!WARNING]
> **The orchestrator is still a placeholder.** The execution workflow below is the contract to build, not something installation enables today.

## Get started

### 1. Install

Use a shell with Bash, curl, tar, and Python 3. The installer checks Hermes and uv and invokes their official installers if they are missing.

```bash
curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash
```

1. Choose a workspace; the default is `~/workspace`.
2. Choose a company command, such as `Acme`, or leave it blank to skip it. Use ASCII letters and digits, beginning with a letter.
3. For a new `master` profile, complete the Hermes setup wizard and choose **Blank Slate**. You own the provider and model choices.

**Success:** the installer reports `Ready` with the profile and workspace. An earlier error means installation is incomplete; some files may already exist.

The installer creates a distribution, **not a Git checkout**. It configures the dedicated `master` profile, shared skills, required CLI toolsets, and the memory-review environment. Your default Hermes profile is not configured. An existing `master` is reused, but theSystem's managed settings still apply.

> [!NOTE]
> **Reinstall is not upgrade.** Existing workspace files are preserved. Re-running installation does not replace them or roll back partial provisioning. Previously installed experimental content stays when the flag is omitted.

<details>
<summary><strong>Installer options</strong></summary>

| Option | Effect |
| --- | --- |
| `--workspace PATH` | Choose the workspace. |
| `--company NAME` | Create the company command; refuses unrelated command-name collisions. |
| `--experimental` | Include experimental rules and skills. |
| `--non-interactive` | Requires `--company` and an existing `master`; cannot perform first-time setup. |
| `--help` | Show usage without installing. |

Example with explicit choices:

```bash
curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash -s -- --workspace "$HOME/workspace" --company Acme --experimental
```

Shared skills are trusted for the workspace, and those needing curator protection are pinned. Concrete model selection remains yours.

</details>

### 2. Open your workspace

If you chose `Acme`:

```bash
Acme
```

**Success:** Hermes opens with `master` in the command's bound workspace, regardless of your current directory. The command lives in `~/.local/bin`, which must be on your shell's `PATH`.

If you skipped the company command, open Hermes with `master` from the installed workspace instead. Describe your goal to the main agent. **Conversation alone does not approve execution or learning.**

## Register a project

A **workspace** contains projects. A **project** holds its knowledge and work records and may contain multiple **source clones**—the repositories being changed.

Create or choose an existing project directory inside your workspace. For the default workspace and example company:

```bash
mkdir -p "$HOME/workspace/payments"
Acme add-project "$HOME/workspace/payments"
```

**Success:** a result with `status: "ok"`, the project path, and whether it was already registered. Registration creates missing `wiki`, `agents`, and `tickets` directories; repeating it preserves content and avoids duplicates.

It does **not** clone repositories, populate knowledge, or configure roles.

| If registration fails | Check |
| --- | --- |
| Missing or invalid directory | The project must already exist; relative paths start from your current directory. |
| Wrong location | Use a project inside the workspace—not the workspace itself, reserved infrastructure, or a source clone. |
| Overlap or unsafe infrastructure | Projects cannot contain one another; existing infrastructure must be real directories, not symlinks. |

Errors return `status: "error"`, a code, and an explanation. `--help` shows usage; `--json` alone does not open chat.

## From request to completed change

**Designed workflow · automated execution is not available yet.**

![Designed workflow: describe and plan, human approval, implementation, independent review, human decision, then merge.](docs/assets/workflow.svg)

| Step | Your action | Expected result |
| --- | --- | --- |
| **1. Plan** | Explain the goal and project; resolve questions. | The main agent gathers context and drafts a ticket specification. |
| **2. Approve** | Review scope, criteria, roles, and blockers. | Proposed tasks become `ready-for-agent`; blockers still apply. |
| **3. Implement** | Start an eligible task through the main agent. | A bounded worker run begins on its own branch. |
| **4. Review** | No intervention required for the review pass. | A fresh reviewer checks the change and records findings. |
| **5. Decide** | Inspect evidence; accept the result or request another attempt. | No automatic rework loop. |
| **6. Complete** | Proceed through the agreed integration process. | The task becomes `done` only after its branch is merged. |

A **ticket** expresses work; its **tasks** divide it into bounded changes. One task is enough when appropriate. Each task changes exactly one source clone; cross-repository work needs linked tasks. A **run** is one implementation-and-review attempt.

### Execution guarantees

- Approval, resolved blockers, valid guidance, and required capabilities are checked **before** execution.
- Independent tasks may run concurrently; a task may have only **one active run**.
- A run records the source clone's current main-branch commit and works on a separate branch.
- Starting returns a stable run identifier and detaches; you need not keep a waiting terminal open.
- The worker stops on conflicting instructions and reports them rather than guessing.
- Review starts after the worker stops, uses a fresh agent, and cannot alter the worker's delivery.
- Control flow belongs to the orchestrator—not an LLM interpreting prose. The main agent uses supported parameters only.

<details>
<summary><strong>Designed command interface — not operational</strong></summary>

```text
./orchestrator start <task>
./orchestrator status [<ticket>]
```

These describe intended interfaces, not commands to use today. A successful review is not an automatic merge.

</details>

## Understand status

**Designed workflow.** You control task approval and disposition; run status is computed from evidence.

| Task state | Meaning |
| --- | --- |
| `proposed` | Awaiting your approval. |
| `ready-for-agent` | Approved; eligible only when blockers clear. |
| `done` | The task branch has been merged. |
| `dropped` | Intentionally abandoned. |

| Computed status | Meaning |
| --- | --- |
| Blocked | A task dependency or external condition remains unresolved. |
| Running | An active run has no terminal result yet. |
| Terminal outcome | The latest attempt's recorded result. |
| Aborted | The process died without recording a terminal result. |

A dependency clears when its task is `done`. An external blocker clears when a human removes it. Approval alone clears neither. The complete terminal-outcome vocabulary is still an open decision.

## Set agent permissions

**Designed execution contract.**

| Agent | Responsibility | Access boundary |
| --- | --- | --- |
| Main agent | Plan with you, monitor work, explain evidence. | Host access; not the worker's containment boundary. |
| Worker | Implement one bounded task. | Per-run container exposing its worktree. |
| Reviewer | Independently check criteria and rules. | Read-only worker tree plus a disposable writable layer for tests. |

Credentials and harness processes remain on the host. Worker commands and edits run in the container. Required CLIs must exist before execution; missing tools do not permit bypassing isolation.

> [!WARNING]
> **MCP grants reach beyond the container.** MCP servers run on the host. Granting one deliberately permits the access it provides; containment does not cancel that access.

### Assign roles

A **role** selects rules, skills, tools, utilities, CLIs, and MCP servers. Use workspace-wide guidance for shared needs and project guidance for specialized needs.

- Each tier has `base`, `worker`, and `reviewer` roles; additional roles may specialize them.
- Apply global before project guidance; within each tier, base, agent role, then additional roles.
- Later same-named entries replace earlier ones; a skill is replaced as a whole.
- **Rules** are enforceable requirements; **skills** are procedures.
- The reviewer must receive every worker rule. Otherwise execution must be rejected. Other capabilities may differ.

The worker receives only the guidance and access it needs. See [CONTEXT.md](CONTEXT.md) for vocabulary and each project's glossary for domain terms.

## Review evidence and learning

### Inspect a run

**Designed workflow.** The terminal record is written once and never edited. It combines the reviewer's structured result with the orchestrator's evidence:

- Starting and resulting commits, terminal outcome, verification results, and agent guidance/capabilities.
- Checks that the worker's tree stayed unchanged during review; a change fails the run.
- Tracked files changed in the reviewer's disposable layer, with lockfile changes flagged because they affect what was tested.

The run branch survives. Temporary worktrees, agent homes, and raw streams do not; they are not committed. **The durable record—not an agent's recollection—is the evidence.**

### Decide what agents retain

Worker and reviewer sessions are fresh. Their experience does not automatically become future guidance.

| Proposal | Your choices | After approval |
| --- | --- | --- |
| Run learning — designed | Approve, reject, or leave pending. | Enforceable requirements become project rules; procedures become project skills, delivered through roles. |
| Hermes memory/skill write — implemented | Review one request at a time; approve, reject, or leave pending. | Hermes applies the reviewed change through its approval mechanism. |

Run-learning decisions are separate from the immutable run record. A rule needs a real incident and a way to check compliance.

For Hermes writes, ask the main agent to review pending requests. **Moving on is not approval.** Unreadable requests stay pending; changed requests need a new review. Review criteria also require explicit human approval.

Remote evaluation may assist, never decide. Only the pending payload may be sent—not conversations, current memories, or installed skills. Requests held locally by the sensitive-data check must not be sent; that check can make mistakes in either direction.

> [!WARNING]
> **Profile coverage is unresolved.** Installation targets `master`; the assisted review workflow names `default`, `implementer`, and `reviewer`. Full `master` integration is not established.

## Maintain the contract

**You own intended behavior.** Agents may draft updates, but changes to that behavior require your approval and a corresponding manual update.

When code, tests, instructions, or other documents disagree with this manual, report the discrepancy. Do not rewrite expectations merely to accommodate a bug or convenient implementation. Keep unimplemented expectations labeled.

Missing approval, unresolved blockers, contradictory instructions, and unavailable prerequisites must stop the affected work—not weaken its safeguards. Completion claims must match observed outcomes in the user's delivery context, not just internal checks.

The glossary supplies vocabulary; [architectural decisions](docs/stuff/decisions.md) supply rationale. Neither replaces this functional contract.

## Open decisions

These are review items, **not silently chosen requirements**:

- [ ] **Agent identity:** reconcile `master`, the older `default` main-agent description, and memory-review profile coverage.
- [ ] **Tracking:** reconcile this repository's GitHub tracking, product-project task/run records, and inconsistent planning-skill workflows. Approved-task execution belongs to theSystem orchestrator, not Hermes Kanban.
- [ ] **Knowledge:** define wiki ingestion, maintenance, retrieval, and human review.
- [ ] **Lifecycle:** settle cancellation, retry, merging, full terminal outcomes, and recovery beyond aborted-run detection.
- [ ] **Distribution:** define upgrades, rollback, uninstall, and isolation between companies sharing a `master` profile.
- [ ] **Manual delivery:** the manual is published with the repository; the current installer does not copy it into installed workspaces.
- [ ] **Platforms and observability:** establish supported environments and a usable telemetry workflow.

---

**Next: human review.** Correct the contract and resolve open decisions before treating this first version as fully approved.
