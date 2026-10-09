Rule: Bootstrap, registration, and provisioning code must derive managed targets
and settings from their canonical declaration. Do not repeat a hand-maintained
list for a category that can gain new members.

Prevents: A new canonical setting, profile target, or skill source being silently
left unconfigured because the integration did not know it had been added.

Enforce with: For each changed install, registry, or provisioning path, identify
the canonical declaration. Read the code and confirm it iterates that declaration,
so a new member needs no edit to the integration. Reject duplicated enumerations
of mutable canonical categories.
