# Comments state why, not what

Rule: Write code that explains itself. Names say what a value holds or what a
function does; structure makes the flow readable top to bottom. When you feel
the need to explain what a piece of code does, treat it as a defect in the code:
rename, or restructure until the explanation is unnecessary. When restructuring
means moving logic between functions or modules, follow the `codebase-design`
skill: do not split code into pass-throughs that only move the complexity. Many
explanatory comments in one place are a red flag that the code is unclear, not a
sign that it is well documented.

A comment is still right for what no code can say: a rejected alternative, an
external constraint, or something that looks arbitrary but is deliberate.

Prevents: Comments that compensate for unclear code duplicate it. The two drift
apart on the next change, readers can no longer tell which one is true, and the
unclear code stays in place.

Enforce with: For each added or changed comment, delete it mentally and reread
the code. If the code is now unclear, fix the code and remove the comment. If
nothing is lost, remove the comment.
