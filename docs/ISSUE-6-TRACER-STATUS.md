## Tracer-bullet orchestrator status — issue #6

The current source is a substantial orchestrator, not the historical placeholder. Its configured path performs ticket-contract validation and admission, worktree/branch creation, contained worker execution, fresh read-only reviewer execution with a disposable test layer, and terminal run evidence. Existing unit tests pass, but this is not equivalent to end-to-end verification under current `MANUAL.md`.

### Four decisions to record

1. The deterministic theSystem orchestrator remains the sole authority for approval, dispatch, lifecycle, integration, and run evidence (accepted in ADR 0001).
2. A run is one worker/reviewer pass; no automatic rework/retry loop. A human-requested retry is a new run.
3. A task becomes done only after a passing run is actually merged into its source clone; approval or review pass alone is insufficient.
4. Worker/reviewer work is container-isolated and provider credentials remain host-owned; missing runtime/container prerequisites fail closed rather than bypassing containment.

### Local review findings

- The runner hard-codes a one-task-at-a-time path, but current code supports retries/caps, dependency dispatch, and integration; do not treat old issue commentary or the historical PLAN baseline as current implementation truth.
- The run's `run.json` is the durable summary consumed by the main agent; no separate `report.md` is required. It is written only after a terminal state. Added regression coverage proves no run record during review and durable terminal record after `passed`.
- Preflight already checks Docker, image availability, worker/reviewer runtime and broker configuration before branch allocation. Added Git, valid-clone, and writable worker/reviewer prompt-storage checks at that same boundary.
- The user-directed Hermes-only manual run is blocked before dispatch. The broker now refuses all Hermes runs with `CREDENTIAL_BROKER_UNSUPPORTED_AUTH` rather than consuming a separate/static API key. Hermes documents `openai-codex` as external OAuth with no API-key env vars, while the shipped OpenAI-compatible subscription proxy only supports Nous and xAI; `hermes proxy providers` confirms that limitation. The required `master` profile is absent, and profiles are deliberately isolated. A compatible, host-side, run-scoped adapter for the selected profile's OAuth lifecycle is not available in the inspected Hermes integration; implementing it safely would require Hermes support or a real selected main profile plus an authorized provider interface. No credential files or values were read. Copilot remains deferred.

### Acceptance still requiring real evidence

Use a minimal approved disposable task and a real Docker-backed Hermes worker/reviewer image; assert approval/blocker/capability checks, stable detached run ID, isolated worker delivery, fresh reviewer with read-only delivery plus disposable test layer, and one immutable terminal `run.json` containing the outcome, commits, structured review, verification results, and guidance/capabilities. Raw streams and agent homes must not persist; no separate `report.md` is part of the contract. Verify failed or requested-change runs stop for human discussion, integration requires human approval, and killing/reconciling a detached run records `aborted` without auto-resume or overwritten evidence. Exercise preflight refusal paths (missing Git, clone, image, broker configuration, prompts, tools); mocks and unit tests do not substitute for the real container path. Copilot parity remains explicitly deferred.
