**Rules guard judgement calls.** When a mistake follows a fixed pattern that a tool can detect (a banned API, an import shape, a file location, a format), propose a linter rule, pre-commit hook or CI check in the project's code to the human; automated tests follow `tests-and-verification-need-human-approval.md`. Write a rule here only for judgement calls that no tool can check. A check lives in a source clone, so it changes the company's code: propose it to the human like any other change.

Each rule is one file with three fields:

- `Rule:` the requirement.
- `Prevents:` the real incident it guards against. No incident, no rule.
- `Enforce with:` the steps a reviewer takes to check compliance by reading the change. Do not restate the rule.
