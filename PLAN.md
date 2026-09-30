# Temporary MVP execution plan — resumed, incomplete

## Resumed rebaseline + blocker burn-down (2026-09-28 08:44 -05:00)

Current true state at resume:

- Git baseline: `master` at `0bb5551`, clean against `origin/master`.
- Test baseline: `python3 -m unittest discover -s tests -q` passed (54 tests, 1 skipped).
- Evidence ledger updated first in [docs/MVP-EVIDENCE.md](docs/MVP-EVIDENCE.md).

Prioritized blocker order for this resumed window:

1. **Remote-distribution install verification** (highest immediate release risk because all prior normal-install proofs used local checkout source).
2. Interactive desktop/account session + normal Herdr launch on supported targets.
3. Hermes normal install + Hermes-in-Herdr verification.
4. Interrupted-install recovery verification.
5. Installed end-to-end retry verification.
6. Native pending-write application verification.
7. Approved wiki ingestion application-path verification.
8. Habit tracker full orchestrator acceptance completion (replanned after earlier exhausted attempts).

Executed immediately (highest-risk first):

- Remote-distribution install verification executed now against the remote install script + codeload archive path in an isolated Ubuntu LTS host environment; recorded PASS artifact `HOST_UBUNTU_REMOTE_DISTRIBUTION_VERIFIED` in the ledger.
- Additional Ubuntu/Arch clean-container reruns attempted for parity but blocked in this runtime by repeated container termination (signal 9 / exit 137) during prerequisite/install flows; recorded as environment blocker with exact evidence.
- Follow-on blocker progress in same resumed window: fixed Hermes installer canonical-config parser dependency (`yaml` import failure) by moving machine-readable canonical entries to `agents/.harness/canonical_config.tsv`; verified local Hermes normal install and Hermes-in-Herdr launch (`LOCAL_HERMES_INSTALL_AFTER_FIX_VERIFIED`).

This plan remains incomplete; MVP is still **not** ready until every remaining acceptance item is verified with target-context evidence.

## Continuation update (2026-09-28 09:40 -05:00)

Completed slices this window:

- Verified interrupted-install recovery in installed host context (`INTERRUPTED_INSTALL_RECOVERY_VERIFIED`).
- Verified installed end-to-end retry path (`INSTALLED_RETRY_E2E_VERIFIED`).
- Verified native pending-write approval application path (`NATIVE_PENDING_APPLY_VERIFIED`).

Unblocking implementation done during habit reattempt work:

- Canonical config parsing for install/bootstrap no longer depends on runtime PyYAML; now sourced from `agents/.harness/canonical_config.tsv`.
- Copilot contained worker/reviewer now set writable cache/home env (`HOME`, `XDG_CACHE_HOME`) and explicit `--reasoning-effort none`.
- Broker now forwards non-sensitive request headers to upstream.

Current top blocker (next to burn down):

- Real provider execution for contained Copilot workers is still failing with upstream `400 Bad Request` after cache/reasoning/header fixes, blocking completion of the habit acceptance app through full orchestrator path.

Update after next slice:

- The upstream `400` blocker is now mitigated by constraining Copilot available tools (`bash`) and increasing broker request budget for long runs.
- New highest blocker is completion quality/stability of the habit acceptance lane: repeated reviewed failures and worker divergence into network-dependent install loops under `--network none`.
- User approved temporary lane with container network egress (`THESYSTEM_CONTAINER_NETWORK=bridge`) for habit acceptance attempts; this removed prior broker/provider rejection classes but has not yet yielded a passing reviewed/integrated habit run.

Immediate next slice:

1. Force a bounded, dependency-free habit implementation path (no package installs) with explicit no-network operational constraints.
2. Run a fresh habit task with shorter timeout budget and deterministic acceptance-oriented tests present at first delivery.
3. Require independent review PASS, integrate, and run browser/runtime verification before claiming objective #8 complete.
4. Then finish remaining non-habit blockers (interactive/account target coverage and approved wiki-apply path) to reach READY.

Current execution stop condition for this lane:

- Do not claim completion until one habit run reaches reviewer PASS, integrates, and is browser-verified.
- If repeated Copilot-worker divergence continues under approved egress, switch to a Hermes worker lane or request explicit human-approved deterministic scaffolding for the habit app task.

## Commit-and-push checkpoint (2026-09-28 07:20 -05:00)

Next session resumes from the published commit; this plan is not superseded. Two phase-2 implementation slices are already delivered and integrated locally. Credential containment is locally certified (2/3 attempts, no third needed); CLI coverage is delivered (1/3). Habit acceptance remains blocked (three prior attempts exhausted in the earlier phase; not relabeled). See the [evidence ledger](docs/MVP-EVIDENCE.md) for the checked-off verified items and the exact unverified blockers to replan onward (interactive Herdr launch, Hermes normal install and Hermes-in-Herdr, remote-distribution install, interrupted-install recovery, installed end-to-end retry, native pending-write application, and approved wiki ingestion application). The authorized continuation deadline below remains 2026-09-28 14:07:48 -05:00. The client-managed `master`/`default` toolset decision was deferred for the next in-context session.

## Authorized continuation (2026-09-28 06:07:48 -05:00)

Juanes authorized a new bounded phase starting 2026-09-28T06:07:48-05:00, deadline 2026-09-28T14:07:48-05:00. This phase allows at most two concurrent implementation workers, at most three **new** attempts per incomplete task, and 60 minutes per attempt. Previous attempts remain historical evidence: habits attempts `cc4765d8927448c29578bfc1845e6902`, `608a130a70ce4543b0dee0d2d65db364`, and `fe6e3883e82149db8b76ebbe760e264c` are exhausted in the previous phase and are never relabeled. New-phase accounting starts at zero per incomplete task and must be recorded with actual run identifiers. The stop handoff below remains the state at resumption, not a completion claim. No push or deployment authorized.

## Stop handoff (2026-09-28 05:34 -05:00)

Juanes asked to stop execution gracefully and publish the current progress. The bounded MVP session is closed early; this document remains because acceptance is incomplete. This is a status record, not authorization for another automatic run. The original eight-hour deadline was 2026-09-28 06:44:13 -05:00, but the stop request supersedes further implementation. See [the evidence ledger](docs/MVP-EVIDENCE.md) and GitHub issue #6 for observed run identifiers and detailed checks.

Verified local slices: contained Hermes and Copilot workers and independent reviewers ran; a genuine Hermes-free Copilot-only task was integrated; todo and Pomodoro were integrated and exercised in a browser, including persistence and both Pomodoro phase transitions; blank Ubuntu installation and limited lifecycle/learning/ingestion probes passed. At stop, 42 repository tests and 18 isolated memory-review tests passed, subject to the final verification entry in the evidence ledger. These are partial results, not MVP acceptance.

Not accepted: the habit tracker exhausted its three attempts and is only an unintegrated preview, with a reviewer finding a UTC/local-date bug and inadequate JavaScript tests. Host-held credentials are not enforced because the worker container receives provider credentials. Removing a Copilot credential from Herdr process arguments invalidated the prior normal-launch proof; the next launch remained blocked awaiting interaction. Full clean normal installation across both supported targets, all CLI journeys, native pending-write application, and approved wiki application are unverified. No production/deployment claim is made. Two isolated acceptance applications remain in separate local clones; their source is not part of this repository push. No additional attempts are authorized by this handoff.

## Purpose and authority

This is the handoff for the next goal-mode session, approved through the preceding discussion with Juanes. Build and verify theSystem MVP; do not conduct another design interview. This document is temporary execution context, not a second permanent manual.

Read AGENTS.md, MANUAL.md, CONTEXT.md, relevant project guidance, and the accepted orchestration ADR before implementation. MANUAL.md is the human-owned functional contract, but its current draft predates the decisions below. Update it to reflect these approved decisions, preserving all unaffected guarantees and truthful availability labels. Do not change requirements to fit implementation limitations. Report genuinely incompatible requirements rather than silently weakening them.

The user delegates implementation choices, including the Copilot CLI/SDK integration design. Ask only if a consequential new decision or human-only action truly blocks work. Otherwise choose the smallest implementation consistent with this agreement.

This handoff initially preceded execution; the stop handoff above supersedes its starting observations and sequence below.

## Problem statement

Installation and portions of the company CLI and memory review exist, but the orchestrator is a placeholder. The user needs a working, independently verified system, a manual memory-review pass tomorrow, and native operation through either Hermes or GitHub Copilot without requiring Hermes on the Copilot-only path.

The final acceptance exercise is to automatically plan and build three disposable web applications through theSystem itself. The apps need to demonstrate the workflow, not production polish.

## Approved scope

### 1. Contract, tracking, and ownership

- Keep human-approved bounded tasks, one source clone per task, per-run worker containment, independent review, immutable terminal run evidence, and completion only after integration.
- theSystem's deterministic orchestrator is the sole authority for approved-task execution. Do not replace it with Hermes Kanban or introduce a competing task lifecycle.
- Company projects use their ticket/task/run tree. Development tickets and WIP for theSystem belong in GitHub. Do not move theSystem's development tracking to company tickets or Hermes Kanban.
- Companies own their data. Do not build a hosted tenancy/privacy service. Avoid accidental mixing of mutable history, memory, or pending learning between company workspaces; do not modify unrelated personal profiles.
- Normalize main-agent naming and installed memory-review coverage. The old master/default/implementer mismatch must not leave the installed main agent outside review coverage. Use worker terminology in the product.
- Keep role ordering and replacement semantics from the manual; reviewers must receive all worker rules. Missing required capabilities or contradictory guidance block the affected task.

### 2. Approval and execution

- Marking a task approved is sufficient execution authorization. The orchestrator starts eligible approved tasks and starts dependent approved tasks when their blockers clear. Do not add a second start confirmation.
- Approval does not override blockers, missing tools, invalid guidance, containment, or required capabilities.
- Material changes to task scope, acceptance criteria, source clone, or permissions invalidate the affected approval.
- A task has at most one active run. Independent tasks may run concurrently.
- Starting a run returns a stable identifier and detaches; a waiting terminal is not required.
- Record the current integration/main-branch commit and use an isolated branch/worktree for the attempt. Do not assume every repository's branch is literally named main or master.
- Run worker commands and edits inside the per-run container. Keep credentials and harness processes on the host under the manual's access model. A Copilot adapter must enforce this too, not just instruct the model to behave.
- Review begins after the worker stops, using a fresh reviewer with read-only access to the worker delivery and a disposable writable test layer. The reviewer cannot change the delivered tree. Detect and fail unexpected changes to that tree.
- Record tracked reviewer-layer changes and flag lockfile changes, since these change what was tested.

### 3. Lifecycle and permissions

Normal product behavior:

- Failed or negatively reviewed attempts stop; another attempt requires the human's request. Do not add an automatic product-wide rework loop.
- Cancellation stops that run's activity and preserves available evidence.
- Detect and reconcile interrupted runs as aborted. Do not silently resume an interrupted attempt or overwrite a terminal record.
- Distinguish passed review, changes requested, execution failure, review failure, cancellation, timeout, and abortion. Passed review is not task completion.
- A passing review is eligible for human integration approval, not automatic merge.
- Resolve conflicts and reverify changes when the integration base moves. Complete only after the verified branch is actually integrated.
- Task blockers clear only by their defined evidence: dependencies complete, or humans resolve external blockers.
- Permit dependency downloads and configured model connections; task-specific external writes, deployments, publishing, production access, and MCP privileges require explicit grants. Workers cannot enlarge their own permissions.
- Preserve run branches and durable run evidence. Remove temporary worktrees, agent homes, and raw streams according to the manual without losing the durable diagnosis of failed or interrupted work. Do not commit transient raw streams or secrets.

Tonight's explicit exception:

- Autonomously plan, implement, test, independently review, retry, and locally integrate the agreed MVP and the three dummy projects.
- Automatically plan and approve the dummy-project tasks for this acceptance exercise. This is not the default for future company work.
- At most two concurrent implementation workers, three implementation attempts per task, sixty minutes per attempt, and eight hours for the overall execution session. Record session start/deadline and attempt accounting; do not reset budgets by relaunching or renaming work.
- Stop affected tasks when their limit is reached; continue eligible independent approved work within the overall budget. Do not silently exceed limits to chase completion.
- Use already-configured model providers. No purchases, new paid services, deployment, source publication/push, destructive cleanup, or unapproved scope expansion. Local commits and integration are authorized for this bounded work. The later explicit stop-and-push request authorizes publishing the current repository changes only; it does not authorize deployment or publishing the separate acceptance clones.
- GitHub is the development tracker; honor this without treating tracking as permission to publish code. Read existing issues and avoid duplicate work. Any tracker writes must be verified by reading back the exact issue/record.

### 4. Memory improvement: manual review ready tomorrow

The success condition is a real first manual pass, not an autonomous-learning platform.

- Collect and expose relevant company main-agent proposals and learning from completed worker/reviewer runs, with their origin visible. Do not import unrelated personal profiles.
- Offer pending review when opening a company session, but allow skipping it. Review one proposal at a time.
- Show the proposed change, evaluator concerns, and explicit approve/reject/leave-pending choices. Moving on is not approval. Evaluators never decide or apply changes for the human.
- Preserve the native Hermes pending-write/apply mechanism for Hermes changes rather than reconstructing approved writes with arbitrary file edits. Changed requests require a new review. Unreadable requests remain pending.
- Provide equivalent human-controlled proposal/review/application behavior in Copilot-only operation without depending on Hermes.
- Run-learning decisions remain separate from immutable run evidence. Approved enforceable requirements become project rules; procedures become project skills, delivered through roles. A rule requires a real incident and a checkable compliance condition.
- Replace the user-facing TYPESAFE_API_KEY configuration with the exact name SYSTEM_ONE_API. Update implementation, installer guidance, examples, and tests consistently. Do not silently continue treating the old name as the canonical setting. This rename does not authorize secret disclosure or edits to personal credential files.
- When SYSTEM_ONE_API is configured, use the existing TypeSafe/Jev remote evaluation path. When absent or unavailable (including timeout, authentication failure, or unusable output), use a fresh headless Hermes evaluator in Hermes mode, or a fresh headless Copilot evaluator in Copilot-only mode.
- Identify the actual evaluator used. If both paths fail, display evaluation unavailable and keep manual review possible. Do not fabricate scores or probabilities. Fallback agents may present concerns with reasons rather than pretend to reproduce calibrated Jev probabilities.
- Company AI use is already approved. Do not add another consent workflow or speculative company privacy subsystem. Still do not expose credentials or include unrelated context unnecessarily. Headless execution is not a promise of local-only inference.
- Evaluation criteria remain human-owned; do not invent a collection of approved criteria. The first agreed clarity criterion is:
  - Question: Is this proposed change unclear to a reader who has only the proposal?
  - Yes: The reader cannot determine what knowledge or procedure is being added, changed, or removed from the proposal itself.
  - No: The proposed knowledge or procedure is understandable on its own.
  - Exclusion: Missing proof of correctness is not, by itself, a clarity problem.
- Present the criterion as advisory. Additional criteria or changes require human approval. The existing clarity criterion is labeled as a testing placeholder; migrate it deliberately rather than presenting an unreviewed placeholder as mature policy.
- Use disposable proposals and isolated agent state for verification. Never approve/reject the user's real pending learning as a test.

### 5. Installation, distribution, company CLI, and Herdr

- Supported MVP targets: Linux x86-64, verified on Ubuntu LTS and the user's Arch/Omarchy environment. Native Windows, macOS, and other architectures are outside this MVP.
- Fresh installation must work with no preinstalled Hermes, uv, Copilot, or Herdr. Obtain required prerequisites through supported installation paths with necessary permission. Human account sign-in remains a human step; never fabricate authenticated success.
- Default installation includes Herdr and the selected agent experience. Support choosing Hermes or Copilot; Copilot-only installation must not install or import Hermes as a hidden prerequisite.
- Implement the exact flag --blank=yes: install only theSystem infrastructure, not Herdr, Hermes, or Copilot, and do not perform model setup.
- In blank mode, non-chat company operations remain usable. Opening chat uses an explicitly selected supported runtime already installed, or reports that none is configured. Never silently install a runtime.
- Normal company launch opens the bound company workspace in Herdr with the selected main agent, independent of the user's current working directory. Keep direct/no-Herdr and headless paths for automation and troubleshooting.
- Herdr displays/manages the session experience, not theSystem's authoritative execution lifecycle. Keep remote access off by default.
- CLI user journeys cover setup, project and source-clone registration, role setup, approval, status, cancellation, retry, evidence review, learning decisions, and integration. Provide useful help and structured errors. Preserve existing safe registration/idempotency behavior.
- Ship the matching MANUAL.md in installed workspaces/distributions. Fix its missing architectural-decisions link.
- Implement safe upgrade, installed-software rollback, and uninstall. Preserve company knowledge, source repositories, work records, and credentials. Software rollback does not undo completed project work. Handle partial/interrupted installation honestly and permit safe recovery.
- Do not claim freshness verification based solely on checking dependencies on this already-provisioned host.

### 6. Native GitHub Copilot adapter

- Implement full native planning, task execution, review, learning, and CLI integration using GitHub Copilot CLI and/or its official SDK. The user delegates the mechanism.
- Hermes is not a dependency in this lane, including for memory-review fallback, orchestration, or task records.
- Translate the accepted functional contract, role guidance, and skill behavior—not merely command spelling. Preserve approvals, containment, independent review, stable evidence, and failure semantics.
- Choose adapter boundaries internally; do not ask the user to design the SDK integration.
- Verify actual supported capabilities against current official documentation and installed tool behavior. A list of advertised SDK features is not proof the adapter enforces isolation.

### 7. Wiki ingestion

- Provide a skill named ingest, building on the existing llm-wiki conventions rather than introducing a parallel knowledge system.
- Read selected raw files from the project's wiki/raw/.
- Show the human the source's facts, obligations, pending matters, and contradictions with existing knowledge.
- Wait for explicit approval before updating the wiki. Merely displaying the extraction is not permission to write it.
- Preserve original raw source content, link claims to provenance, reuse relevant pages, and maintain the wiki's index/log conventions.
- Record obligations as knowledge, not automatically approved execution tasks.
- Do not add automatic crawling, a mandatory vector database, or autonomous background wiki rewriting.

### 8. Documentation and housekeeping

- Run the documentation-maintenance skill after completed runs and a final housekeeping pass at the end of this work.
- Remove only redundant context and owned temporary artifacts; preserve unique knowledge, pending learning, approved behavior, evidence, and the user's pre-existing changes.
- Changes that alter meaning beyond the agreement remain proposals, not housekeeping.
- MANUAL.md owns permanent approved user-facing behavior. Do not retain this temporary plan as a competing contract or copy implementation trivia across context documents.
- Keep this plan available throughout execution/recovery. Remove it only after its accepted contract has been incorporated and the final handoff/evidence is durable. If work stops incomplete, retain it with accurate status.

## Acceptance applications

Create separate dummy company projects/source clones, isolated from real company data. Select ordinary lightweight web technology yourself.

1. Todo list: add, edit, complete/uncomplete, and delete tasks; persist state across reloads.
2. Customizable Pomodoro: configurable work and break durations, start, pause, reset, and correct transitions; persist settings across reloads.
3. Habit tracker: define habits, record daily completion, and view history; persist state across reloads.

Autonomously plan the applications and build them THROUGH theSystem's implemented approval, dispatch, worker, independent reviewer, evidence, and integration path. Do not hand-build them outside the orchestrator and then backfill run records. Their appearance can be basic; their stated interactions must work.

Across these exercises, prove both Hermes and Copilot execution, including at least one genuine Copilot-only environment with Hermes absent. Record which app/run exercises which runtime. Validate browser-visible interactions against the real running applications; screenshots or mocked model responses alone are insufficient.

The apps are the final end-to-end acceptance exercise, not a substitute for the installation, learning, CLI, and failure-path checks below.

## Execution sequence

1. Reorient and inspect: recheck live Git state, existing code/tests/issues, documentation, model access, available container tooling, and current official agent documentation. Preserve pre-existing manual changes. Record the real execution deadline.
2. Translate this agreement into MANUAL.md and a bounded implementation breakdown. Reconcile existing GitHub work rather than creating a second development tracker. Make no unrequested source push or deployment.
3. Establish working vertical execution slices with deterministic orchestration, durable evidence, contained worker execution, and independent review. Build on existing test seams where possible; use TDD and repository conventions.
4. Complete the learning-review path, selected-runtime adapter parity, ingestion skill, installation/distribution lifecycle, and company CLI/Herdr experience. Independent bounded tasks may run concurrently within the limit.
5. Run isolated safety/lifecycle/integration tests and clean-install experiments. Fix root causes and re-run affected verification.
6. Plan and build all three acceptance apps through theSystem, independently review them, locally integrate passing work, and exercise their actual web interfaces.
7. Perform the documentation-maintenance and housekeeping pass. Re-run relevant verification after changes. Report exact verified outcomes and remaining blockers without silently converting scope into future work.

## Acceptance evidence checklist

Keep a concise evidence ledger during execution: requirement, actual invocation/test, exit/result, durable artifact or run identifier, and verified/failed/blocked status. Do not mark a requirement verified based on an agent's self-report.

- [ ] Approved contract reflected in MANUAL.md; unaffected guarantees preserved; local documentation links valid.
- [ ] Existing test suite and relevant new tests pass; final diff/compile/lint checks appropriate to the changed code pass.
- [ ] Fresh normal install verified without preinstalled Hermes, uv, Copilot, or Herdr on supported target environments.
- [ ] Copilot-only install and execution verified with Hermes absent.
- [ ] --blank=yes verified to omit runtimes/Herdr and retain non-chat CLI usability.
- [ ] Herdr-backed company launch and direct/no-Herdr behavior exercised.
- [ ] Project/source registration, role setup, approval, automatic eligible dispatch, status, cancellation, retry, review, and integration exercised.
- [ ] Unapproved tasks, unresolved blockers, missing prerequisites, invalid roles, and containment failures refused.
- [ ] One-active-run constraint and concurrent independent work checked.
- [ ] Worker/reviewer isolation, unchanged worker delivery, and reviewer-layer/lockfile evidence checked.
- [ ] Cancellation, timeout, negative review, interrupted-run reconciliation, and immutable terminal records checked.
- [ ] Integration verified against the actual current base; completion only after integration.
- [ ] Real headless learning evaluation works, including Copilot fallback without Hermes.
- [ ] Remote evaluation exercised when authorized credentials/service are available; otherwise explicitly blocked, not simulated.
- [ ] Evaluator failure/unavailability remains visible and manual review still works.
- [ ] Disposable approve/reject/leave-pending and changed/unreadable proposal handling verified; actual user pending learning untouched.
- [ ] ingest presents facts/obligations/pending matters and waits for approval before updating; sources preserved.
- [ ] Upgrade, rollback, uninstall, and interrupted-install recovery preserve user/company data.
- [ ] Todo app planned and built through theSystem; browser interactions and persistence verified.
- [ ] Pomodoro app planned and built through theSystem; timing/settings interactions and persistence verified.
- [ ] Habit app planned and built through theSystem; daily history and persistence verified.
- [ ] Both runtimes represented by genuine completed acceptance runs and independent review evidence.
- [ ] Final docs/housekeeping pass complete with no lost obligations, user changes, or evidence.

Mocks are appropriate for bounded unit tests, but never replace real authentication, real evaluator calls, clean installation, agent execution, or browser acceptance evidence. If a prerequisite is missing, attempt safe alternatives and then record the precise blocker. Do not call the MVP done with any named acceptance requirement unverified.

## Known starting observations (recheck; not promises)

- Repository: /home/juancrfig/workspaces/theSystem, GitHub origin https://github.com/juancrfig/theSystem.git.
- Branch observed: master. MANUAL.md was already modified by the user before this handoff; do not reset it. PLAN.md is the temporary new handoff.
- orchestrator currently only prints a placeholder greeting.
- Existing areas include install, bootstrap, company_cli.py, tests, agents/skills/memory-request-review, agents/skills/research/llm-wiki, and docs/ADRs/0001-approved-task-execution-orchestrator.md. Inspect actual contents rather than guessing APIs.
- MANUAL.md links to missing docs/stuff/decisions.md; the accepted orchestration decision is under docs/ADRs/.
- Docker responded successfully. Hermes, Codex, Copilot, and Herdr were found. GitHub authentication and Codex ChatGPT login were reported available. Copilot model access and a complete Hermes invocation were not verified.
- The hermes-agent skill could not load because it was quarantined. Do not disable the safety mechanism to load it. Use authoritative https://hermes-agent.nousresearch.com/docs for required Hermes facts, and report a real blocker if necessary. Do not guess headless/profile/install flags.
- Web extraction failed because the configured search backend could not extract pages; web search successfully retrieved official docs. Use another permitted retrieval route where needed, not fabricated documentation.
- GitHub officially documents Copilot SDK at https://docs.github.com/en/copilot/how-tos/copilot-sdk and CLI at https://docs.github.com/en/copilot/reference/copilot-cli-reference. Herdr installation/integrations are documented at https://herdr.dev/docs/.

## Final handoff

Report what is verified, what changed, where the applications can be opened, how to begin tomorrow's manual memory review, and any exact blockers or budget-limited incomplete work. Do not claim installation readiness from unit tests or product completion from attractive apps. No promises of morning success; deliver observed evidence.

The user will launch this plan in a new goal-mode session. Merely writing this plan does not start execution. In a plain CLI, do not promise push notifications or assume a background process will survive host shutdown. Use runtime-supported bounded background execution only when needed and preserve honest state on interruption.
