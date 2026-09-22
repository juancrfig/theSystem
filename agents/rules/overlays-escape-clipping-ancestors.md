# Overlays escape clipping ancestors

Rule: A user-facing overlay that is meant to extend beyond its trigger — a
dropdown, popover, calendar, tooltip, menu, drawer, or modal — must remain
visible and usable outside its containing surface for its entire open lifetime.
Its visibility must not depend on an ancestor with clipping overflow.
`z-index` does not override overflow clipping.

An anchored overlay must remain associated with its current trigger position
through scrolling, resizing, and layout changes, or close. It must close when
its trigger is no longer visible or present; it must never remain stranded over
unrelated content. Visible overlays must respect the available viewport and
retain access to their controls. Placement and dismissal must preserve focus
semantics and modal ownership, without undoing the user's scroll. Animation
must not prolong an invalid placement or delay necessary dismissal.

Equivalent anchored overlays within a surface or flow must share the defined
opening direction and alignment. A different direction is allowed only when
the available viewport or access to controls requires it; that exception must
follow the same placement policy for all equivalent overlays.

An ancestor may clip its own scrolling, animation, or decorative content. That
is not permission to clip an interactive overlay that belongs outside it.

Prevents: A clipped overlay may appear correctly layered until it extends
beyond its container. Moving it outside that container can expose further
failures when scrolling leaves it detached from its anchor or outside the
viewport. Inconsistent placement between equivalent overlays makes the
interface unpredictable.
