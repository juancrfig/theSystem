---
experimental: true
---

Rule:
Before declaring a change complete, check its immediate consequences for the person or system that will consume it. Verify that the next intended action is possible in the actual delivery context, not merely that the underlying artifact is correct. Keep verification within the requested scope, and disclose anything that could not be checked.

Prevents:
The installer handoff required user correction because its presentation did not support the intended use. The subsequent fix was judged through source-level checks rather than evidence from the user-facing result.

Enforce with:
Identify the immediate consumer, the next intended action, and the context in which it occurs. Check whether the verification evidence covers that interaction. Reject completion claims that substitute internal correctness for an unverified consumer-facing outcome.
