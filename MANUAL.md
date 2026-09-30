# theSystem · User manual

Build software with AI agents. Keep control of the requirements, permissions, and result.

> [!IMPORTANT]
> **Human-owned contract · draft awaiting review.** This manual is the highest authority for intended functionality: what the human wants and what AI must build. Publication does not mean every expectation is approved or implemented.

[Get started](#get-started) · [Projects](#register-a-project) · [Workflow](#from-request-to-completed-change) · [Status](#understand-status) · [Permissions](#set-agent-permissions) · [Learning](#review-evidence-and-learning) · [Open decisions](#open-decisions)

## What works today

| Capability | Availability |
| --- | --- |
| Installation, company command, project registration | Implemented |
| Shared planning skills and assisted memory/skill review | Implemented in Hermes; coverage and fallback are being verified |
| Experimental rules and skills | Opt-in with `--experimental` |
| Automated task admission, isolated execution, independent review, run records | **Partial local implementation; MVP incomplete** |
| Copilot runtime, task execution, and learning integration | **Deferred backlog; outside the current Hermes-focused MVP scope** |
| Upgrade/rollback/uninstall, wiki ingestion | **Partial local verification; MVP incomplete** |

“Implemented” describes repository capability, not a fresh deployment certification.

> [!WARNING]
> **The execution contract is not fully certified.** Local contained Hermes and Copilot runs, independent reviews, and two browser-tested apps are documented in [MVP evidence on GitHub](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5908905757). The third app and several installation/learning guarantees remain incomplete; the workflow below remains the intended contract, not a blanket availability claim.

<details>
<summary><strong>Recorded verification and remaining gaps</strong></summary>

This summary uses historical GitHub evidence, not a fresh deployment check. Results apply only to the tested source, runtime, and environment; a passed probe or a closed issue does not certify the whole capability. See the [MVP evidence ledger](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5908905757), [installation/lifecycle record](https://github.com/juancrfig/theSystem/issues/24), and [Copilot adapter record](https://github.com/juancrfig/theSystem/issues/22) for provenance and scope.

| Area | Recorded evidence | Remaining gap |
| --- | --- | --- |
| Installation | Fresh local-distribution blank and Copilot-only installs passed in Ubuntu 24.04 and Arch base containers, with Hermes absent. A remote-distribution Copilot install passed on an isolated Ubuntu LTS host. | Default Hermes clean installation and first-time setup, remote-distribution parity across targets/runtimes, and actual Omarchy desktop coverage remain uncertified. |
| Software lifecycle | Isolated blank-mode upgrade, rollback, and uninstall probes preserved data fixtures and user-edited content on Ubuntu and Arch. A separate interrupted-install/rerun probe passed in an isolated host context. | These probes do not certify every runtime, interruption point, or real company-data migration. |
| Task execution | Contained Hermes/Copilot runs, independent reviews, a narrow Hermes-free Copilot integration, and two integrated browser-tested apps are recorded. An installed retry probe dispatched a new run; both attempts ended in execution failure. | Full execution/safety and native Copilot parity are not certified. The habit app has no accepted reviewed integration. Later adapter records retain acceptance gaps; earlier sampled runs do not establish full parity. |
| Learning | Disposable Hermes/Copilot fallback evaluations and a native Hermes pending-write approval/application probe passed in isolated state. | Installed-main-agent coverage, complete Copilot-only learning/application, and full evaluator acceptance remain incomplete; a later Copilot evaluator attempt lacked authentication and reported unavailable. |
| Wiki ingestion | A disposable proposal preserved raw files and deferred writes pending approval. | The human-approved wiki application path remains unverified. |

The records describe different historical slices. An item listed as untested in one slice is not evidence that another slice's narrower probe failed, nor does that probe close the broader acceptance gap. No additional user testing outside GitHub is claimed.

</details>

## Get started

### 1. Install

Supported MVP targets are Linux x86-64 on Ubuntu LTS and Arch/Omarchy. Fresh installation must obtain missing prerequisites through supported paths; no preinstalled Hermes or uv is assumed. Hermes is the sole integrated runtime for the current MVP. Native Copilot task execution and learning integration are deferred backlog work; they are not install options or part of the current MVP scope. `--blank=yes` selects infrastructure only. Human account sign-in remains a human step.

```bash
curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash
```

1. Choose a workspace; the default is `~/workspace`.
2. Choose the name of the main command; the default is `company`. Use a single word with standard English characters.
3. Complete setup for your selected installation mode:

| Mode | Setup |
| --- | --- |
| Hermes (default) | For a new `master` profile, complete the Hermes setup wizard and choose **Blank Slate**. An existing `master` is reused. You own the provider and model choices. |
| Infrastructure only (`--blank=yes`) | No agent runtime or model setup is installed. Company operations that do not require an agent runtime remain available. |

**Success:** the installer reports `Ready` with the runtime and workspace (`none` is the runtime in blank mode). An earlier error means installation is incomplete; some files may already exist. `Ready` is not proof of authenticated chat or full MVP certification.

The installer creates a distribution, **not a Git checkout**. In Hermes mode, it configures the dedicated `master` profile, shared skills, required CLI toolsets, and the memory-review environment. Your default Hermes profile is not configured. An existing `master` is reused, but theSystem's managed settings still apply. Blank mode installs only theSystem infrastructure.

> [!NOTE]
> **Installation is only partially verified.** See [recorded verification and remaining gaps](#what-works-today) for the tested contexts. The intended lifecycle safely upgrades, rolls back installed software, and uninstalls without deleting company knowledge, source repositories, work records, or credentials. Rollback does not undo completed work.

<details>
<summary><strong>Installer options</strong></summary>

| Option | Effect |
| --- | --- |
| `--workspace PATH` | Choose the workspace. |
| `--company NAME` | Create the workspace-bound command for task/orchestrator and supporting operations; refuses unrelated command-name collisions. |

| `--experimental` | Include experimental rules and skills. |
| `--blank=yes` | Install theSystem infrastructure only; no agent runtime or model setup. See the verification summary for tested targets. |
| `--non-interactive` | Requires `--company`. Hermes mode also requires an existing `master`; it cannot create a new profile through the setup wizard. Blank mode does not require a Hermes profile. |
| `--help` | Show usage without installing. |

Example with explicit choices:

```bash
curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash -s -- --workspace "$HOME/workspace" --company company --experimental
```

In Hermes mode, shared skills are trusted for the workspace, and those needing curator protection are pinned. Concrete model selection remains yours.

</details>

### 2. Use your company command

If you chose `company`:

```bash
company --help
```

**Success:** the command shows its supported operations. It lives in `~/.local/bin`, which must be on your shell's `PATH`, and is bound to the installed workspace regardless of your current directory.

The company command is a non-chat interface for ticket/task and orchestrator operations, project/source-clone registration, role configuration, evidence, and learning review. Calling it without arguments shows help. It does not open an interactive agent session; `launch` and `--direct` are not supported.

Open any interactive planning agent separately. **Conversation alone does not approve execution or learning.** Runtime configuration remains available for task execution and learning evaluation, not company-command session launch.

## Register a project

A **workspace** contains projects. A **project** holds its knowledge and work records and may contain multiple **source clones**—the repositories being changed.

Create or choose an existing project directory inside your workspace. For the default workspace and main command:

```bash
mkdir -p "$HOME/workspace/payments"
company add-project "$HOME/workspace/payments"
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

**Approved workflow · partial execution evidence, not full certification.**

![Designed workflow: describe and plan, human approval, implementation, independent review, human decision, then merge.](docs/assets/workflow.svg)

| Step | Your action | Expected result |
| --- | --- | --- |
| **1. Plan** | Explain the goal and project; resolve questions. | The main agent gathers context and drafts a ticket specification. |
| **2. Approve** | Review scope, criteria, roles, and blockers. | Approved eligible tasks start automatically; dependent approved tasks start when blockers clear. No second start confirmation. |
| **3. Implement** | Monitor an approved task. | A bounded worker run starts on its own branch and returns a stable identifier without keeping a terminal waiting. |
| **4. Review** | No intervention required for the review pass. | A fresh reviewer checks the change and records findings. |
| **5. Decide** | Inspect evidence; accept the result or request another attempt. | No automatic rework loop. |
| **6. Complete** | Proceed through the agreed integration process. | The task becomes `done` only after its branch is merged. |

A **ticket** expresses work; its **tasks** divide it into bounded changes. One task is enough when appropriate. Each task changes exactly one source clone; cross-repository work needs linked tasks. A **run** is one implementation-and-review attempt. Company projects keep their own ticket/task/run tree; development work on theSystem is tracked on GitHub. The deterministic orchestrator alone owns approved task execution, not the chat agent or another task board.

### Execution guarantees

- Approval, resolved blockers, valid guidance, and required capabilities are checked **before** execution.
- Changing task scope, acceptance criteria, source clone, or permissions invalidates its approval. Missing tools or contradictory guidance stop the affected task rather than relaxing a requirement.
- Independent tasks may run concurrently; a task may have only **one active run**.
- A run records the source clone's current integration-branch commit and works in an isolated branch/worktree; the branch need not be named `main` or `master`.
- Starting returns a stable run identifier and detaches; you need not keep a waiting terminal open.
- The worker stops on conflicting instructions and reports them rather than guessing.
- Review starts after the worker stops, uses a fresh agent, and cannot alter the worker's delivery.
- Worker commands and edits run inside a per-run container. The reviewer reads the delivered tree without changing it and uses a disposable writable layer for tests. Unexpected delivery changes fail review; tracked test-layer and lockfile changes are reported.
- A passing review only makes the branch eligible for human integration approval. When the base moves, conflicts are resolved and the resulting change is reverified; completion follows actual integration.
- Control flow belongs to the orchestrator—not an LLM interpreting prose. The main agent uses supported parameters only.

<details>
<summary><strong>Illustrative command interface — not current CLI usage</strong></summary>

```text
./orchestrator start <task>
./orchestrator status [<ticket>]
```

These describe intended interfaces, not commands to use today; they do not describe the partially implemented CLI's current syntax. A successful review is not an automatic merge.

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

A dependency clears when its task is `done`. An external blocker clears when a human removes it. Approval alone clears neither. Runs distinguish passed review, changes requested, execution failure, review failure, cancellation, timeout, and interruption/abortion. A failed or negatively reviewed attempt stops; retry requires a human request. Cancellation preserves available evidence. Interrupted attempts are reconciled as aborted, not silently resumed or overwritten.

## Set agent permissions

**Designed execution contract.**

| Agent | Responsibility | Access boundary |
| --- | --- | --- |
| Main agent | Plan with you, monitor work, explain evidence. | Host access; not the worker's containment boundary. |
| Worker | Implement one bounded task. | Per-run container exposing its worktree. |
| Reviewer | Independently check criteria and rules. | Read-only worker tree plus a disposable writable layer for tests. |

Credentials and harness processes remain on the host. Worker commands and edits run in the container. Required CLIs must exist before execution; missing tools do not permit bypassing isolation.
Dependency downloads and configured model connections are permitted. Task-specific external writes, deployment, publication, production access, and MCP privileges require explicit grants; agents cannot enlarge their permissions.

> [!WARNING]
> **MCP grants reach beyond the container.** MCP servers run on the host. Granting one deliberately permits the access it provides; containment does not cancel that access.

### Assign roles

A **role** selects rules, skills, tools, utilities, CLIs, and MCP servers. Use workspace-wide guidance for shared needs and project guidance for specialized needs.

- Each tier has `base`, `worker`, and `reviewer` roles; additional roles may specialize them.
- Apply global before project guidance; within each tier, base, agent role, then additional roles.
- Later same-named entries replace earlier ones; a skill is replaced as a whole.
- **Rules** are enforceable requirements; **skills** are procedures.
- The reviewer must receive every worker rule. Otherwise execution must be rejected. Other capabilities may differ.
- Company workspaces keep mutable knowledge, history, and pending learning separate. Unrelated personal profiles are not imported into company review.

The worker receives only the guidance and access it needs. See [GLOSSARY.md](GLOSSARY.md) for vocabulary and each project's glossary or glossary map for domain terms.

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

Use `company learning inventory`, `company learning show`, and `company learning decide` to inspect and decide pending requests. Each proposal shows its origin, content, evaluator concerns, and the explicit choices above. Requests remain pending until an explicit decision; opening an agent session is not part of this command's responsibilities.

The first approved advisory criterion asks: **Is this proposed change unclear to a reader who has only the proposal?** Yes means the reader cannot determine what knowledge or procedure is added, changed, or removed from the proposal itself. No means it is understandable on its own. Lack of proof of correctness alone is not a clarity defect. The older generic clarity criterion was a testing placeholder, not mature policy. Further criteria require your approval.

The optional remote evaluation setting is `SYSTEM_ONE_API`. When configured, use the existing TypeSafe/Jev path; if absent, timed out, rejected, or unusable, use a fresh headless Hermes evaluator. Report the evaluator actually used. If neither works, show evaluation unavailable and keep human review possible. Fallback concerns carry reasons, not invented probabilities. Company AI use is already approved; no extra consent screen is required.

Remote evaluation may assist, never decide. Only the pending payload may be sent—not conversations, current memories, or installed skills. Requests held locally by the sensitive-data check must not be sent; that check can make mistakes in either direction.

> [!WARNING]
> **Current profile coverage remains unverified.** The installed main agent must be included in company review. Historical `master`/`default`/`implementer` names must not leave it out.

### Ingest selected project sources

The intended `ingest` skill reads selected files from a project's `wiki/raw/`, presents facts, obligations, pending matters, and contradictions against existing knowledge, then **waits for explicit approval** before updating the wiki. Raw sources remain unchanged; claims cite their provenance, existing pages are reused, and the index/log are maintained. Obligations are knowledge, not automatically approved execution tasks. No automatic crawling or background rewriting is part of this workflow. **Proposal-only evidence exists; approved application remains unverified.**

## Maintain the contract

**You own intended behavior.** Agents may draft updates, but changes to that behavior require your approval and a corresponding manual update.

When code, tests, instructions, or other documents disagree with this manual, report the discrepancy. Do not rewrite expectations merely to accommodate a bug or convenient implementation. Keep unimplemented expectations labeled.

Missing approval, unresolved blockers, contradictory instructions, and unavailable prerequisites must stop the affected work—not weaken its safeguards. Completion claims must match observed outcomes in the user's delivery context, not just internal checks.

The glossary supplies vocabulary; [architectural decisions](docs/adr/0001-approved-task-execution-orchestrator.md) supply rationale. Neither replaces this functional contract.

## Open decisions

These are review items, **not silently chosen requirements**:

- [ ] Verify the approved MVP execution, safety, installation, adapter, learning, and UI acceptance exercise before changing availability labels to implemented.
- [ ] Determine an observability workflow and any later-platform support beyond this Linux x86-64 MVP separately.

---

**Approved MVP decisions are reflected above; implementation availability is still evidence-dependent.** Unaffected draft material remains subject to human review.
