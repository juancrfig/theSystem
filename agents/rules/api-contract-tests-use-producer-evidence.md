# API contract tests use producer evidence

Rule: A new or changed API request or response mapping must have an executable
test that passes producer-derived evidence through the production serializer or
deserializer and asserts the API-bound values. Preserve property names,
nesting, and value types. Use synthetic values and retain a non-sensitive
source reference plus a version or capture date. A fixture invented from
consumer code, or a test that directly constructs the parsed model, does not
establish API compatibility.

Prevents: Consumer-defined fixtures can repeat an incorrect field name,
nesting, or value type. Static analysis and those tests may pass while real
requests or responses fail.

Enforce with: For each changed request or response mapping, review for
producer-derived evidence and an assertion sensitive to that mapping. Run the
test offline: the previous incorrect mapping must fail and the corrected
mapping must pass. Without producer evidence, report API compatibility as
unverified.
