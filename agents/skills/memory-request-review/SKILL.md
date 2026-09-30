---
name: memory-request-review
description: "Use when reviewing pending Hermes memory or skill writes across default, implementer, and reviewer. Inventory native requests, evaluate and show one ASCII dashboard at a time, and require an explicit human decision."
---

# Assisted memory-request review

Use this skill at the start of a new conversation to review pending writes for
`memory` and `skills` in the company `master` profile (and legacy compatible
profiles when present). It does not create or maintain another queue.

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

`./install` prepares the environment with the pinned `typesafe-sdk` version in
`requirements.txt`. The review script discovers it automatically from its own
location, regardless of the current directory or skill symlinks. Do not ask the
user to export variables or interpret a missing variable as a missing
installation. `HERMES_MEMORY_REVIEW_PYTHON` is only an optional explicit choice
of another prepared interpreter. Do not install dependencies while running a
review; if the environment is missing, instruct the user to run install.

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
