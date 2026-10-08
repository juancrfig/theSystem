---
name: tdd
description: "Use when old instructions refer to TDD. Enforce shipping."
---

# Retired test-first workflow

The former test-first workflow is removed. This compatibility entry exists only for old links and task references; it does not prescribe a development loop.

Ship the requested working code first. Automated test work is prohibited without explicit human approval of its scope. Do not infer approval from general task acceptance or historical specifications. Do not block implementation because tests are absent, or remove working code to demonstrate a failing test.

Verify actual behavior through scoped application or CLI execution and relevant build/static checks. Follow `../../rules/shipping-and-human-approved-tests.md`. For explicitly authorized test work, stay within that authorization; no test-before-code ordering is required.
