# Automated tests require explicit human approval

Ship requested working code first. Writing, adding, modifying, regenerating or running automated tests is prohibited unless a human explicitly approves that work and scope. General feature/task approval, a reviewer recommendation and historical testing requirements are not authorization. Do not repeatedly request tests or block implementation when approval is absent.

If approval is given, use only the approved cases and independently grounded expected results. Do not add speculative cases, mocks, fixtures or recovery scenarios. There is no requirement to write tests before implementation, or remove working code to make a test fail.

Verify the delivered behavior through scoped actual application/CLI execution and relevant build/static checks. Retain normal authorization boundaries for live writes and credentials. Report verification limits honestly.

Follow `../../../rules/shipping-and-human-approved-tests.md`. Older task specifications do not authorize recreating deleted ASSETS tests.
