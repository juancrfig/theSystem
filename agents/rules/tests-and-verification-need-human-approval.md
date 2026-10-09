Rule:
Tests are a scarce good. Write, change or run automated tests only at the end of development, and only when the
human explicitly approves each test. Verification follows the same principle: do not run the application, builds,
linters, type checkers or smoke checks to confirm your own work unless the human explicitly asks for it. Approval of a
spec, a task split or a task is not approval of tests or verification. Never block or delay delivery because tests or
verification are missing, and never claim that something was tested or verified when it was not.

Prevents:
Agents spent most of each task writing speculative tests and verification harnesses that nobody asked for, delaying
working code and growing suites the human did not want to maintain.

Enforce with:
Read the diff for added or changed test files, fixtures, mocks, snapshots and test configuration. Each one must trace
to an explicit human approval quoted in the task. Read the worker's report for test or verification runs that the
task did not request.
