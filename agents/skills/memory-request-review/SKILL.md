---
name: memory-request-review
description: "Use when reviewing pending Hermes memory or skill writes. Covers the default (main agent), worker and reviewer profiles; shows one evaluated request at a time and requires an explicit human decision."
---

# Assisted memory-request review

Use this skill at the start of a new conversation to review pending writes for
`memory` and `skills` in theSystem's Hermes profiles: `default` (the main agent),
`worker` and `reviewer`. It does not create or maintain another queue.

## Evaluators

Each criterion in `criteria.json` is asked about the request's literal payload by one evaluator:

- **Jev** (TypeSafe System One), when `SYSTEM_ONE_API` is set in the environment or the
  workspace `.env`. It returns a probability per criterion.
- **Headless Hermes** otherwise: a fresh one-shot session in the main agent's profile, with no
  tools and no workspace context. It returns concerns with reasons, never numbers.

## Authority limits

- Do not approve or reject based on a probability, missing signals, or a Jev
  error.
- Do not modify a pending request, split its operations, or reconstruct a write
  with file or memory tools.
- Do not send conversations, current memories, installed skills, or summaries to
  Jev. The only permitted remote state is the literal `payload` object from the
  native pending request.
- If the review is `RETAINED LOCALLY`, do not expose or copy the detected
  value and do not send it to Jev. Explain that the detector can have false
  positives and negatives.
- With `NO CRITERIA`, do not call Jev or invent scores: begin human review of
  real cases.

## Batch start

The review runs in an isolated interpreter at `.agents/memory-review` in the
workspace. If the review script reports that the interpreter is unavailable
(first use, or after a Hermes upgrade changed its Python), prepare it once:

```sh
python3 agents/skills/memory-request-review/scripts/prepare_environment.py
```

It finds Hermes's Python through the `hermes` launcher on PATH, creates a
virtualenv on that Python (with `uv` if available, including the copy Hermes
bundles, otherwise `venv` + `pip`), installs the pinned `typesafe-sdk` from
`requirements.txt`, and links Hermes's own modules into it. Rerunning it is
safe. Never install dependencies any other way, and never during a review.

The review script finds the interpreter from its own location, regardless of
the current directory or skill symlinks. Do not ask the user to export
variables. `HERMES_MEMORY_REVIEW_PYTHON` is only an optional explicit choice of
another prepared interpreter.

```sh
python3 \
  agents/skills/memory-request-review/scripts/review_memory_requests.py inventory
```

Report the counts of `memory`, `skills`, and unreadable records. Unreadable
records cannot be approved; leave them pending and show their identity/error.

Review one request at a time. `show` sends only the selected request to Jev (the
others wait their turn) and renders its already-evaluated panel; there is no
prior step that shows the proposal and evaluates it later.

```sh
python3 \
  agents/skills/memory-request-review/scripts/review_memory_requests.py show \
  --position 1
```

Copy the panel inside a code block, without added comments or JSON. For the
human view, show only the profile name in the header and hide technical
identifiers (`pending-id`, `record_sha256`, `payload_sha256`). Keep those values
internally for `decide`. The panel shows `Target` (`memory`, `user`, or
`skill:<name>`), each operation as `ADD`, `DELETE`, or `REPLACE` with its text
(`−` old, `+` new) without detailing where it lands in the file, and each Jev
question with its probability (higher = more likely problem). Do not average or
convert results into a quality score. Show at most one request per turn.

## Decision per request

After showing exactly one panel, offer: **approve**, **reject**, **leave pending**,
or **discuss/propose a criterion**. Moving forward is not a decision.

Only after the person explicitly responds with `approve` or `reject`, use the
identity and `record_sha256` captured while reviewing the request: profile,
subsystem, and native ID. Do not select again by position. The hash prevents
acting on a pending request that was modified, replaced, or already resolved:

```sh
python3 \
  agents/skills/memory-request-review/scripts/review_memory_requests.py decide \
  --profile default --subsystem memory --pending-id '<reviewed-id>' \
  --decision approve --human-decision \
  --expected-record-sha256 '<hash-shown-during-review>'
```

Use `--decision reject` to reject. Verify the response: `success: true`,
`pending_removed: true`, and, for an approval, the Hermes `native_result`.
If it fails or the hash changed, do not repair, recreate, or apply a variant;
return to inventory and request a new review.

## Staleness check

`show` also checks, locally and read-only, whether the request still fits its target, and
shows a warning above the scores:

- **Old text no longer present**: a replace or delete names text the current skill or memory
  file no longer contains. Hermes cannot apply it cleanly, or that part was already rewritten.
- **Target changed after this request**: the target was edited after the request was made.
  Any edit counts, so this means "check carefully", not "outdated".

**Automatic rejection (human-approved rule):** run `sweep` at the start of every review
session, before showing any request. It rejects every request with *Old text no longer
present* and prints one line per rejection (target, summary, created_at); report that list to
the human. *Target changed* alone never triggers it, because approving one request flags every
other request for the same skill. Sweep decisions are logged with `decided_by: auto`.

These are facts, not criteria: they are never sent to Jev. The check cannot tell whether a
request is still true about the code; only the human or a reader of the code can.

## Criterion learning

The questions sent to Jev live only in:

```text
agents/skills/memory-request-review/criteria.json
```

Every edit to `criteria.json` (adding, rewording, versioning, or removing a
criterion, or changing `catalog_version`) requires explicit human approval of
the exact change text before it is written. Show the proposed diff and wait for
an explicit `yes`; your proposal, a Jev score, or prior approval of another
change does not count as approval.

After a rejection, ask whether the case warrants a general condition. Do not
add one by inference.

Each approved criterion requires `id`, `version`, `question`, `context`,
`definition.yes`, and `definition.no`, plus `exclusions` and `examples` when
they add clarity. State one condition per question and preserve the direction:
a higher probability means a higher probability of the described problem.
Increase `version` when the meaning changes.

After adding or changing a criterion, show/evaluate all remaining pending
requests again. Do not reuse results if the payload, criterion version, or
effective model identity changed. Retain previous results only when all four
dimensions match.

## Verification

Run the isolated tests before declaring the delivery verified:

```sh
"${HERMES_MEMORY_REVIEW_PYTHON:-.agents/memory-review/bin/python}" \
  agents/skills/memory-request-review/tests/test_review_memory_requests.py
```

A real Jev test requires at least one approved criterion, an eligible request,
and `SYSTEM_ONE_API` in the environment or the ignored checkout-root `.env`
(see `.env.example`); the environment takes priority. If any are missing,
report that blocker; never simulate an evaluation. Test native integration with
a temporary `HERMES_HOME`, never by approving or rejecting real pending writes
for coverage.
