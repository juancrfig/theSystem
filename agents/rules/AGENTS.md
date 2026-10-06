**Mechanical rules become automated checks.** When a mistake follows a fixed pattern that a tool can detect (a banned API, an import shape, a file location, a format), prevent it with a check in the project's code: a linter rule, a test, a pre-commit hook or a CI job. Write a rule here only for judgement calls that no tool can check. A check lives in a source clone, so it changes the company's code: propose it to the human like any other change.

Each rule is one file with three fields:

- `Rule:` the requirement.
- `Prevents:` the real incident it guards against. No incident, no rule.
- `Enforce with:` the steps an agent or reviewer takes to check compliance. Do not restate the rule.
