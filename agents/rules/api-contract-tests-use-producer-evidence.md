Rule: Before claiming a fact about an API, inspect producer-derived evidence and state
its scope: affected endpoint, environment, and version or capture date when
known. Source checkout findings describe that checkout, not deployed behavior;
ticket requirements describe intent, not runtime output. Without sufficient
evidence, state an unverified hypothesis rather than a confirmed cause.

Verify API mappings against producer evidence and actual scoped execution.
Automated test work is prohibited without explicit human approval.
For approved tests, use production serialization/deserialization. Preserve property names,
nesting, and value types. Use synthetic values and retain a non-sensitive
source reference plus a version or capture date. A fixture invented from
consumer code, or a test that directly constructs the parsed model, does not
establish API compatibility or deployed producer behavior.

Prevents: Consumer-defined fixtures can repeat an incorrect field name,
nesting, or value type. A constructed payload with deliberately missing fields
can be misreported as proof that a deployed API omits them; a stale checkout
can be mistaken for the deployed contract. Static analysis and such tests may
pass while real requests or responses fail.

Enforce with: Before an API diagnostic conclusion, identify the evidence that
supports that exact claim and its limits. Prefer existing captures and saved
artifacts. If evidence cannot be obtained, ask human for assistance.
Inspect producer evidence and actual API-bound values. Do not require a failing
test before implementation. Run automated tests only within explicit human
authorization. Without producer evidence, report API compatibility as unverified.
