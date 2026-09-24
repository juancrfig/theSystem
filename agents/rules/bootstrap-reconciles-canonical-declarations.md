# Reconcile canonical declarations

Rule: Bootstrap, registration, and provisioning code must derive managed targets
and settings from their canonical declaration. Do not repeat a hand-maintained
list for a category that can gain new members.

Prevents: A new canonical setting, profile target, or skill source being silently
left unconfigured because the integration did not know it had been added.

Enforce with: For each changed bootstrap, registry, or provisioning path, identify
the canonical declaration. Verify that adding a valid fixture member changes the
result without editing the integration. Reject duplicated enumerations of mutable
canonical categories.
