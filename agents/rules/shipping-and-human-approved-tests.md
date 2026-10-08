# Ship working code; automated tests require human approval

Deliver the requested working behavior first. Use the smallest implementation that satisfies the user's actual need. Do not expand scope with hypothetical failures, coverage goals, or speculative robustness.

Automated test work is prohibited unless a human explicitly approves that work and its scope. Do not write, add, modify, regenerate, or run automated tests without that approval. This includes test fixtures, mocks, snapshot suites, regression harnesses, and delegated test work. General feature approval, task-split approval, a reviewer recommendation, or historical test requirements do not implicitly authorize tests. Carry the exact human authorization into any worker brief.

There is no test-before-code requirement. Never delay implementation to create a failing test, remove working code to demonstrate a failing test, or block delivery because unapproved tests are absent. If no tests are authorized, continue implementing; do not turn lack of test approval into a blocker or repeatedly ask for tests.

Verification is still required: exercise the delivered behavior with the actual application or CLI, inspect the result, and use relevant build, syntax, lint, or type checks. These checks do not authorize a new test suite. Use existing evidence rather than constructing hypothetical cases. Respect existing authorization boundaries for live writes, secrets, and shared systems. State exactly what could not be verified.

This policy supersedes older testing requirements in skills, templates, task specifications, and run context. Apply it to workers and reviewers as well as the main agent. Do not edit historical run evidence to pretend the old instructions never existed.
