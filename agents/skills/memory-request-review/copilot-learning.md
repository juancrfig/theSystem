# Copilot-only learning review

Use this workflow for company learning proposals when the selected runtime is Copilot. It is deliberately separate from Hermes pending-write storage and must not import Hermes modules.

1. Collect a proposal from a completed worker/reviewer run, or a main-agent change suggestion. Keep it separate from immutable `run.json`; store the proposal under the owning project's `.thesystem/learning/pending/` directory.
2. Show one proposal at a time, including its origin, literal proposed change, and evaluator concerns. Do not modify a rule, skill, or run record while presenting it.
3. Evaluation is advisory. Prefer `SYSTEM_ONE_API` using the existing TypeSafe/Jev path. If missing, timed out, rejected, or unusable, start a fresh headless Copilot evaluator in an isolated home with only the proposal and approved advisory criteria. Report which evaluator actually ran. If both paths fail, report evaluation unavailable and continue to allow human review. Never synthesize probabilities.
4. Possible credential-bearing proposals stay local and are not sent to any evaluator. State the detector category without displaying the suspected value.
5. Require an explicit human decision for each proposal: approve, reject, or leave pending. Moving to another proposal is not approval. Bind a decision to the proposal's content hash; if content changed, require review again.
6. An approved procedure may be applied as a project skill, delivered through roles. An approved enforceable requirement may be applied as a project rule only when it cites a real incident and a checkable compliance condition. Reject or leave pending without writing. Never update `run.json`.

## Copilot evaluator contract

Invoke a fresh Copilot CLI process with a clean temporary `COPILOT_HOME`, no custom instructions, no MCP servers, and no tools enabled. Send only the literal proposal and advisory criteria. Accept only a structured list of concerns with a reason for each; invalid output is evaluation unavailable. Do not treat evaluation as a human decision.

## Scope boundary

This procedure describes semantics; it does not claim that a native run-learning queue, application command, or real Copilot evaluator is implemented. The native Hermes pending-write workflow remains separate and must continue to use Hermes's native application mechanism.
