# 06: Tracer-bullet orchestrator run

**What to build:** the thinnest `./orchestrator` that takes one golden ticket from the sandbox
project through the whole path and ends in a labelled state:

validate ticket → create worktree → implementer run → reviewer run → `report.md` → run record.

Crude is fine: a hard-coded minimal bundle, no parallelism, no budgets beyond a fixed timeout.
Later tickets deepen each stage. This one proves the path exists.

**Why:** build the loop before the furniture (analysis 3.1). The orchestrator is 3 lines today,
while bootstrap and memory review are polished. The legacy attempt never ran a feature end to end.

**Blocked by:** 03, 04, 05

**Status:** needs-decision

## Decisions

1. **How agents are invoked.** Recommended: call Hermes directly per run
   (`hermes chat --query-file … --oneshot --format stream-json`, with the profile's home), not
   through the kanban dispatcher. Kanban brings its own control flow (requeues, auto-decompose),
   and that is the control flow the orchestrator must own.
2. **Where the agent process runs.** Recommended: Hermes on the host, with its terminal backend in
   a per-run container and toolsets restricted per role. This is the setup that was exercised.
   Credentials stay on the host. The first run must prove with a probe that file tools are
   container-scoped too. If they are not, move the Hermes process into the container.
3. **Language.** Recommended: Python, like the existing tests. Bash is fine for bootstrap. It is
   not fine for a state machine.
4. **Run storage.** Recommended: `.runs/<run-id>/` in the workspace, ignored by git, holding
   `run.json`, `report.md`, and the raw agent streams, plus one line per run in
   `.runs/index.jsonl`.

## Lessons carried from the legacy workspace (as criteria, not code)

- [ ] There is no retry or attempt parameter. A run is one pass (legacy: `--attempt-limit`
      bypassed the documented policy).
- [ ] `report.md` is created exclusively, only in a terminal state, by the orchestrator (legacy:
      a report was created while the state was still `ready_for_reviewer`).
- [ ] Before any model call, the orchestrator checks that the worktree exists, the container has
      the clone's toolchain (at least `git`), and every path named in the agent prompt exists
      inside the container (INST-142: `/task-spec` versus a host path, missing worktree,
      missing `git`).
- [ ] Nothing decomposes the ticket into child tasks.

## Acceptance

- [ ] Each decision above is answered.
- [ ] The clean-pass golden ticket ends in `passed`, and its change is on the run's branch.
- [ ] The run record holds: ticket, clone, base and head commits, model per role, start and end
      times, terminal state, and the agent streams.
- [ ] Killing the orchestrator mid-run leaves a run record in state `aborted`, not a silent gap.
