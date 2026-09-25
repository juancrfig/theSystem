# Foundations: theSystem through the cost lens

Status: analysis, 2026-09-24. Sources: this repo, `../legacy-workspace`, Hermes (default, implementer,
reviewer profiles, kanban), Codex and Claude Code history. Evidence marked *(verified)* was
checked directly against files or databases; other evidence comes from the research pass over
session history.

The tickets in `issues/` implement what this document concludes. This file is working material,
not durable documentation: promote to rules, ADRs, or the wiki only what passes the `writing-docs`
ladder.

## 1. The cost model

Every practice pays down a cost. When the cost moves, the practice must move with it.

| Cost | Human era | Agent era | What your history shows |
|---|---|---|---|
| Writing code and docs | High | ~0 | A skill, a config, a state machine: one session each |
| Rewriting | High | ~0 | The orchestrator was designed twice (legacy workspace, then theSystem) at no token pain |
| Keeping copies in sync | High | Low **if a machine checks** | Without a check, copies drifted every time (section 3.5) |
| Verification (human attention) | Medium | **The bottleneck** | Every serious incident was caught by a human re-reading |
| Spec clarity | Medium | **Dominant** | Desvio formula re-decided 4+ times; INST-142 path mismatch rediscovered run after run |
| Context window | n/a | **Hard budget** | Handoff docs used as the standard escape hatch, dozens of times |
| Coordination of parallel writers | Low (few writers) | **High** | Shared profile config, shared memory, shared kanban loop |
| Trust | Built slowly | **Must be built structurally** | Your trust tightened over 6 weeks: "prove it", "confirm to me" |

Your own sentence already states the key idea: *"A skill asking the agent to not touch a file is a
desire, not a gate."* (Codex, 2026-09-10). Most of what follows expands that sentence.

## 2. What you already do right (keep it)

- **Deterministic control flow.** "No LLM decides control flow inside the orchestrator" is the
  correct answer to the legacy WIP, where `--attempt-limit` silently bypassed the documented
  retry policy *(verified, legacy review1.md)*.
- **Rules need an incident.** `Prevents:` is a scarcity mechanism. It stops rule bloat, which is
  the knowledge-side version of abstraction bloat.
- **The docs ladder** (drop → rule → ADR → ledger → wiki). It makes *keeping* a fact expensive
  now that *producing* one is free.
- **Bright lines over judgement calls.** The comment rule was exploited while it allowed a
  judgement call. The rewrite named the incident and removed the judgement.
- **Deterministic gates worked every time you built one**: the surface-preservation sentinel,
  the comment pre-commit hook, the rule-field hook.
- **Human stays in control during bring-up.** Single-pass runs, no auto-fix loop. That is the
  right call until you can measure the loop (section 3.2).
- **Reviewer independence.** Fresh-context reviewers caught what implementers rationalized.

## 3. The revaluations, derived from your own evidence

Each item: the old practice, the cost it paid down, what changed, your evidence, and the ticket.

### 3.1 Build the loop before the furniture

- **Old practice:** build each infrastructure piece well, one at a time, because rewriting is
  expensive.
- **What changed:** rewriting is cheap. The expensive thing is not knowing whether the *whole*
  works.
- **Evidence:** `orchestrator` is 3 lines (`echo "Hello, Orchestrator!"`) and every role list in
  `orchestrator.yaml` is empty *(verified)*. `bootstrap` is 341 lines, with a spinner checklist UI.
  `memory-request-review` is 717 lines plus an external LLM judge, and its ASCII card went through
  ~20 revision turns. A working-ish orchestrator (`workflow_support/pipeline.py`, with tests) sits
  untracked in the legacy workspace *(verified)* and was re-derived from scratch in a 7-hour interview. The
  INST-142 rehearsal never attempted the feature itself: 4 infra failures came first.
- **Revaluation:** a crude end-to-end tracer bullet on a toy project beats a polished component.
  Carry forward the *lessons* of the legacy orchestrator (its review findings), not its code.
  Code is cheap to rewrite. Lessons are not.
- **Tickets:** 06 (tracer bullet), and the prior-art criteria inside 06–09.

### 3.2 The eval set is the new spec

- **Old practice:** unit tests verify code; humans verify behaviour by using the product.
- **What changed:** the system's main output is *agent behaviour*, and nothing measures it.
- **Evidence:** no outcome label exists in any store (Hermes, Codex, Claude Code). The reviewer
  never reviewed a real diff. Codex "success/fail" summaries are self-graded by the same model.
  There is one criterion in `criteria.json`, and it is a placeholder *(verified)*.
- **Revaluation:** your rule format already contains the eval set. **No incident, no rule →
  no incident, no eval.** Every rule's `Prevents:` incident becomes a seeded violation in a
  sandbox project. The reviewer must catch it. `Enforce with:` states how.
- **Tickets:** 05 (sandbox and golden tickets), 10 (eval runner).

### 3.3 Verification is the bottleneck: pay human attention once, then gate

- **Old practice:** review each change carefully.
- **What changed:** agents produce changes faster than a human can read them. Attention must be
  spent on building checks, not on repeating checks.
- **Evidence:** 20 closed MTBT efforts, zero harvested, even after the rule was written three
  times *(verified, legacy ADR-no-ticket-tracking)*. The comment rule was gamed through a
  judgement call. A dependency bump passed an existing rule, because rules only fire at review
  time.
- **Revaluation:** anything that matters becomes a deterministic check that runs every time.
  LLM judgement is kept for what no check can express, and it is labelled as judgement.
- **Tickets:** 01 (check gate), 08 (isolation verified per run), 11 (harvest as a gate).

### 3.4 Copy instead of share: per-run locality beats shared mutable state

This is DHH's choke-point argument, and your system shows it clearly.

- **Old practice:** one shared configuration that everybody uses, so nothing is duplicated.
- **What changed:** copies are free, and shared mutable state is where parallel agents collide
  and drift.
- **Evidence *(verified)*:** both worker profiles hard-code one client's Docker image
  (`client-db-inspect`) and volumes. Worker profiles have `memory_enabled: true` and carry legacy
  memories that have nothing to do with their role. `SOUL.md` is identical in all three live
  profiles, but it is not the canonical `agents/.harness/SOUL.md`. Skills reach profiles through
  persistent global symlinks. That conflicts with the per-run bundle that `AGENTS.md` describes.
  The reviewer's "read-only" mount was writable in every smoke run: the reviewer's own write probe
  succeeded 4 of 4 times.
- **Revaluation:** each run gets its own bundle, its own container, and for the reviewer, **its
  own disposable copy** of the worktree. The goal is "the reviewer cannot alter what it reviews",
  and a hash of the implementer's tree before and after enforces it better than a mount flag. It
  also lets the reviewer run tests, which a read-only mount breaks. The things you keep single are
  the *declarations*: `orchestrator.yaml`, the canonical profile config, the rules. That is DRY
  for knowledge. The per-run copies are duplication of shape, and they are free.
- **Tickets:** 03 (canonical profiles), 07 (bundle builder), 08 (isolation).

### 3.5 Knowledge DRY needs a machine that checks the pointers

- **Old practice:** docs rot, so humans keep few of them.
- **What changed:** docs are now *input* to agents. A broken pointer is a bug in the program, not
  a typo.
- **Evidence *(verified)*:** `AGENTS.md` points at `wiki/index.md`,
  `wiki/practices/knowledge-system.md` and `agents/utils/`, and none of them exist. Agents
  rediscovered this in at least four sessions. The tier model appears in three places.
  `context-files.md` was updated; `code-review` still describes a third, clone-scoped tier and a
  `./preflight` that was removed. `to-spec` says both "do not publish externally" and "publish it
  to the project issue tracker". The memory-review spec puts the criteria in a global rule, but
  the implementation moved them to `criteria.json`. In the legacy workspace, a Spanish copy of 6 rules already
  contradicted the original.
- **Revaluation:** state each fact once, point to it everywhere else, and let a pre-commit check
  prove that every pointer resolves.
- **Tickets:** 01, 02.

### 3.6 The spec is the expensive artifact

- **Old practice:** a spec is a rough guide; the developer fills the gaps while coding.
- **What changed:** an agent fills gaps at machine speed, confidently, in the wrong direction.
- **Evidence:** the INST-142 task told agents to read a host path while the spec was mounted
  somewhere else, and smoke runs hit it repeatedly. A board had no default workdir. Skills named in
  a task were not installed on the profile. None of these were code problems. All of them were
  unstated assumptions in the task.
- **Revaluation:** a ticket is a contract that the orchestrator validates *before* it spends a
  token, the same way it refuses a rule mismatch. Every acceptance criterion states how it is
  verified.
- **Ticket:** 04.

### 3.7 Control flow must terminate

- **Old practice:** retries and requeues are free, so be generous.
- **What changed:** an unattended agent loop has no natural end, and nobody watches it.
- **Evidence *(verified)*:** kanban task `t_ed81287a` has logged 1,237 `respawn_guarded`
  events since 2026-09-22, and it is still going. Rate-limit and auth requeues do not count toward
  `consecutive_failures`, so no breaker ever trips. Research also found one Codex session that
  burned 26.5M tokens from one user message, and `/goal` budgets used once in ~900 prompts.
- **Revaluation:** every run ends in exactly one labelled terminal state, within a time and token
  budget that the orchestrator enforces, not the agent. Hermes gives you the parts: `chat
  --oneshot --max-turns --run-budget --usage-file --format stream-json`.
- **Ticket:** 09.

### 3.8 The trace is the product

- **Old practice:** logs exist for debugging.
- **What changed:** when an agent does the work, the trace is the only thing a human can verify.
- **Evidence:** worker sessions record $0 cost (subscription billing). Rate-limit errors were shown
  as "Authorization error" and became the title of 18 sessions. No task links to the commit it
  produced.
- **Revaluation:** one structured run record per run: ticket, clone, base and head commits, bundle
  manifest with hashes, model per role, tokens, duration, terminal state, findings tagged with rule
  ids, and later the human verdict. Start with a JSON Lines file. OpenTelemetry (named in the
  README) can come later, once you know which questions you ask.
- **Tickets:** 06 (minimal record), 10 (history and scoring).

### 3.9 The learning loop must be a gate, and its input must shrink

- **Old practice:** people remember to write down lessons.
- **What changed:** nobody remembers, and agents over-generalize. You wrote this yourself in the
  README Decisions section.
- **Evidence:** 0/20 harvests. The memory queue holds 10 memory and 21 skill requests, with a
  placeholder criterion. The research pass also found a pending background-review proposal
  (`pending/memory/bcd2040a.json`) that would replace "don't paste credentials" with the file and
  line where a QA password is stored.
- **Revaluation:** fold the human's review of a run into one pass that does three jobs: verdict
  (eval label), harvest proposal (zero is normal), and next action. Reduce the input instead of
  building a better reviewer for it. Worker profiles do not need autonomous memory, because they
  learn only through the bundle.
- **Tickets:** 03 (worker memory off), 11 (verdict and harvest).

## 4. How to keep finding revaluations

1. For any practice, ask what cost it paid down and whether that cost moved (section 1).
2. **Let the run history be your friction log.** Every run ends in a labelled state with a
   one-line human note. Weekly: group by terminal state and by rule id, and turn the top category
   into a ticket. This is the concrete answer to README problem 4, "How will the system improve
   over time?".
3. Tag each rule and decision with the cost it pays down. When models get cheaper, contexts get
   larger, or a check becomes automatable, revisit exactly the rules tagged with that cost.
4. When an agent re-derives something that already exists, treat it as a finding. Here, the
   orchestrator was designed twice.

## 5. Risks not ticketed yet

- **Parallel runs share state outside the worktree**: dev database, ports, the
  `sqlserver_default` network, git identity. Worktrees isolate git only. Decide before running two
  tickets at once.
- **Provider limits** (429, 402, 403 across Copilot, OpenRouter, OpenCode) were the largest
  source of failed runs. A run must fail fast and labelled (`infra_blocked`), never requeue
  silently.
- **Tirith false positives** ("Nested executable body could not be resolved") appear in both
  worker profiles. They are indistinguishable from real blocks in the logs.
- **Text-only review misses rendering bugs.** The bootstrap duplicated-row bug was caught only
  when you pasted real terminal output.
- **Model routing is manual by decision** (`chore: leave model routing to users`). Fine, but the
  run record must at least store which model each role used.
- **Vendored skills without provenance.** grill-me, to-spec, tdd, triage, codebase-design and
  diagnosing-bugs come from mattpocock/skills, with no upstream version recorded.

## 6. Do now (human operations, minutes each)

- Stop or archive kanban task `t_ed81287a` (INST-142 "repaired pipeline smoke").
- Reject pending memory `bcd2040a` (secret-location memory).
- Delete `legacy-workspace/MTBT/.scratch/ado.pat` (plaintext PAT, acknowledged as "left alone") and
  rotate it.
- Confirm that the theSystem GitHub remote is private, or run ticket 01's company-data scan
  before the next push.

## 7. Ticket map

| # | Ticket | Force | Blocked by |
|---|---|---|---|
| 01 | Workspace check gate | Verification, knowledge DRY | — |
| 02 | Resolve knowledge drift | Knowledge DRY | 01 |
| 03 | Canonical worker profiles | Shared state, trust | — |
| 04 | Ticket contract | Spec ambiguity | — |
| 05 | Sandbox project and golden tickets | Evals | 04 |
| 06 | Tracer-bullet orchestrator run | Loop before furniture | 03, 04, 05 |
| 07 | Bundle builder | Locality, contract choke point | 06 |
| 08 | Enforced isolation | Trust, verification | 06 |
| 09 | Budgets and terminal states | Termination | 06 |
| 10 | Eval runner and run history | Evals, observability | 05, 09 |
| 11 | Verdict and harvest gate | Learning loop | 06 |
| 12 | Dogfood theSystem through the orchestrator | All | 07, 08, 10, 11 |

Status values: `ready-for-agent`, or `needs-decision` when a human must answer the listed
decisions first. Each decision comes with a recommendation.
