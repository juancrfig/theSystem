# Review visible-text translations

Rule:
For every new or modified user-facing component, flow, or translation resource, review both translation coverage and translation key reuse across all application-owned visible text. Include reused components and their defaults in that flow, even when their files are outside the diff. A translation lookup is not proof that its key exists, and existing entries across supported locales do not justify creating redundant keys. Confirm coverage in every locale the application supports. Missing translations, hardcoded fallback text that bypasses localization, and unjustified duplicate translation keys block approval. Respect an explicitly approved single-language requirement; do not invent new supported locales. Distinguish application copy from user or server-owned content rather than assuming that dynamic content is translated.

Prevents:
- A date-placeholder styling change passed code review although its reused date selector referenced a missing translation key and silently fell back to another language. Reviewing only the changed styling missed visible behavior inherited from an unchanged component.
- Duplicate boolean keys passed code review because coverage checked only that keys were defined across supported locales, failing to detect that identical boolean semantics were already provided by existing canonical translation keys.

Enforce with:
- Discover supported locales from the application's declarations and localization loader before judging coverage.
- Trace visible labels, placeholders, buttons, validation messages, errors, tooltips, accessibility text and dialogs in the changed flow to their actual localization lookup and resources. Follow reused components, defaults and dynamically selected keys; do not limit this pass to changed lines.
- Confirm that each application-owned message exists and is nonempty in every supported locale, and that its lookup resolves through the actual loader. Check interpolation arguments and plural/select variants where used. A literal fallback must not hide an absent translation.
- Report missing coverage with the consumer and resource locations, affected locale and user-visible impact. Put failures on the Standards axis as hard findings. Do not silently change the intended wording or exempt required copy.

### Mandatory Translation Key Reuse Pass (After Locale Coverage, Before Verdict)
- For every added or modified translation key in the candidate, inventory the full key path and callsite.
- Search the entire existing translation catalogs and shared resources across the whole application (not merely within the candidate module) for exact and semantic reusable equivalents in ALL supported locales, including reused defaults. Case or spacing differences can hide duplicates; same text alone is not semantic proof—verify identical domain meaning.
- Prefer an existing canonical key over a new module-specific key for the same meaning, even if the preexisting key belongs to another module. Reuse canonical keys without forcing whole-catalog reorganization; consider introducing a common namespace only when an equivalent is genuinely missing across all existing resources; move existing consumers without duplicate aliases when approved necessary.
- Do not merge different meanings or change wording just because strings match; verify semantics and consumers rather than equate same text with same meaning.
- Verify every cited alternative's full key path and values in the actual catalogs, and trace its consumers before judging equivalence. A different module, namespace, or wording alone does not justify a new key when the underlying user-facing action, validation condition, or failure is the same. For a claimed semantic difference, cite the concrete difference in source behavior and what the message communicates.
- For every newly introduced key, require concrete evidence of searched existing alternatives and an explicit reason why no existing key can be reused.
- Trace all consumers across the codebase (including dynamic constructions) before removing redundant entries, and update every supported locale file together in the same change.
- In the review report, include the mandatory evidence table:
  `Candidate Key / Consumer | Existing Candidate Alternatives | Status (reuse | new justified | duplicate | unresolved) | Locale Evidence and Reason`
- Explicitly block Standards approval (hard finding) for unjustified duplicates, unresolved inventory/search, or missing report evidence. The fact that all keys are present across supported locales or that coverage passed does not establish reuse.
- Report coverage and reuse independently; reject any generic PASS that lacks separate evidence for both passes.
- In the review report, name the locales and flow reviewed. If required resources, callsite inventory, or dynamically constructed keys cannot be traced, report the gap as unresolved and withhold approval; do not claim complete translation coverage or reuse.
- Perform this pass strictly by reading source and resources. It does not authorize application runs, automated tests, linters or new verification scripts.
