---
experimental: true
---

Rule:
Before declaring a change complete, think through its immediate consequences for the person or system that will consume it. Design for the next intended action in the actual delivery context, not merely for the correctness of the underlying artifact. Do not run checks to confirm this unless the human asks; state any consequence you could not reason through.

Prevents:
The installer handoff required user correction because its presentation did not support the intended use. The subsequent fix was judged through source-level reasoning about the artifact rather than about the user-facing result.

Enforce with:
Identify the immediate consumer, the next intended action, and the context in which it occurs. Read the change and check that it supports that interaction. Reject changes that serve internal correctness while leaving the consumer-facing outcome unaddressed.
