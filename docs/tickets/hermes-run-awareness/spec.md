# F11 — Hermes run awareness

Tracker: https://github.com/juancrfig/theSystem/issues/37

Status: ticket, two-slice implementation plan, and named checks approved. Implementation is deferred to a new machine. This document authorizes planning only; do not dispatch, install, or publish a release as part of this handoff.

## Problem Statement

The main agent and human cannot see detached theSystem runs as live activity in Hermes. The launcher exits before the worker and reviewer finish, so its completion notice is misleading as a run-completion signal.

## Solution

Ship a theSystem-owned Hermes integration through installation and updates. Show a compact panel above the Ink TUI status bar, let the agent discover runs, and deliver terminal results automatically to the originating main-agent conversation.

## User Stories

1. As the human, I want active runs to appear automatically so I can see work continuing.
2. As the human, I want worker and reviewer stages so I know who is working.
3. As the main agent, I want current-workspace discovery so I do not need the human to supply evidence paths.
4. As the main agent, I want a completion signal without a user message so I can report a result promptly.
5. As the human, I want approval, requested changes, and infrastructure failure distinguished so I can decide what to do.
6. As the human, I want busy-session queueing so notifications do not interrupt work.
7. As the human, I want unavailable-session events retained so restarting does not silently discard results.
8. As the human, I want duplicate protection so normal polling does not repeat notices.
9. As the human, I want finished cards retained until dismissed so results remain visible.
10. As the human, I want stale records identified without repair so the display does not pretend a dead orchestrator is working.
11. As the human, I want profile and conversation isolation so results do not leak into other sessions.
12. As the maintainer, I want this shipped by theSystem so it survives updates without a private Hermes fork.

## Implementation Decisions

- Serves F11, with installer/update integration through F1/F10. Keep task records authoritative; notification bookkeeping is delivery state, not another task database.
- Limit discovery and display to the configured workspace. Label cards as theSystem runs, not native Hermes subagents.
- Use supported Hermes plugin tools/hooks, message injection, and ambient TUI widgets. Do not patch Hermes core or use private session queues directly.
- Bind launches to the durable originating session key and profile. Do not assume terminal environment exposes these; verify the plugin-to-launch handoff before implementation. A run without a known origin must not be sent to an arbitrary session.
- Persist stable completion identifiers and pending delivery state after terminal run evidence is durable. Signal each run ending in pre-done, changes-requested, or failed; launcher exit is not completion. Account for abandoned-run reconciliation.
- A profile-scoped plugin observes pending local events and invokes supported message injection. An idle target starts a turn; a busy target queues it. Retain rejected/unavailable deliveries for the same origin.
- Distinguish host acceptance from completed processing. Do not promise transactional exactly-once delivery across crashes; implement duplicate protection and document any remaining admission/acknowledgment window.
- Keep the panel small and responsive, show role/stage and outcome, and retain finished results until dismissal. Dismissal affects display only, not task status or delivery acknowledgment.
- A running record without a held dispatcher lock is possibly stale, not automatically failed by the integration. Read-only discovery must not invoke the run command to reconcile state.
- Installer targets the actual main profile, not a hardcoded default. Do not install notification consumers into worker/reviewer profiles. Preserve existing configuration and authorization boundaries.
- Minimal notifications contain task/run identifiers, outcome, and evidence location, not transcripts, credentials, or raw customer data. Results are evidence, not instructions or approval.
- No automatic merge or retry. No live profile changes during design; installation and TUI lifecycle requirements must be made explicit before live verification.

## Testing Decisions

The following named checks are approved. Additional cases require human approval; actual test changes still require human scrutiny before acceptance. Prefer existing subprocess-level installer and orchestrator tests with controlled worker/reviewer executables. Exercise plugin behavior through its public registration/injection contract and widget behavior through the supported SDK. Keep tests offline and use temporary workspaces/profiles, not unrelated live company runs.

Approved cases:
1. Controlled worker-to-reviewer run shows both stages; each of the three terminal outcomes creates a matching completion event after durable evidence. Launcher exit alone creates none.
2. Originating idle session receives a real turn; busy session queues without cancellation; another profile or session receives nothing.
3. Unavailable origin retains its event; resuming the same session delivers it; repeated observations and restart do not routinely duplicate acknowledged notices. Explicitly exercise and report the acknowledgment crash window.
4. Active and finished cards render through the widget SDK; finished cards persist until dismissal; dismissal does not mutate tasks or suppress an undelivered notice.
5. Unlocked running record appears possibly stale; malformed/incomplete records fail safely without state repair or blocking orchestration.
6. Install/reinstall/update deploy integration to the resolved main profile, leave worker/reviewer profiles untouched, and preserve origin/notification state.

Run existing repository checks: python3 -m unittest discover -s tests. Add executable JavaScript syntax/SDK checks for the widget if Node is available. Finish with a controlled end-to-end Ink TUI session proving automatic wake-up; mocks alone cannot establish real delivery. No live company services or credentials.

## Out of Scope

Native Hermes subagent lifecycle integration; Hermes core patches; remote/network notification servers; Telegram or other messaging delivery; automated merge/retry; release publication; repairing task state from the display; copying company-specific settings into theSystem.

## Further Notes

Source inspection confirmed supported in-process plugin message injection. theSystem must supply the local event bridge. A context hook alone only runs on an existing turn and cannot wake an idle conversation. Hermes accepts injected messages but does not thereby prove completed processing. The integration must be verified against the installed Hermes API before promising restart behavior.

## Approved implementation split

1. **Live run visibility and discovery.** Deliver current-workspace worker/reviewer progress, agent discovery, retained finished cards with dismissal, and possibly-stale handling. Ship through installation and updates. No dependency.
2. **Automatic completion delivery.** Depends on slice 1. Bind each launch to its main-agent conversation and profile; deliver terminal outcomes automatically, queue while busy, retain unavailable deliveries across restarts, and protect against duplicates. No automatic merge or retry.

## New-machine handoff

Read AGENTS.md and FEATURES.md F11 first. Resume from this approved spec; no executable task files or integration implementation were created in this handoff. Verify the new machine's supported Hermes plugin injection and widget APIs, resolve session-origin capture, and exercise the acknowledgment crash boundary before claiming reliable automatic delivery. Development stays in theSystem source. Commit/push of this planning record does not authorize a release or deployment.
