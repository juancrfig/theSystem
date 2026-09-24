# Overlays escape clipping ancestors

Rule: An overlay meant to extend beyond its trigger — dropdown, popover,
calendar, tooltip, menu, drawer, or modal — must not be clipped by an ancestor.
`z-index` does not override overflow clipping; render the overlay outside the
clipping surface. An ancestor may clip its own scrolling or decorative content;
that does not extend to an overlay that belongs outside it.

Once outside its container, an anchored overlay must follow its trigger through
scrolling, resizing, and layout changes, or close. It closes when its trigger
scrolls out of view or is removed. It stays within the viewport with its
controls reachable. Positioning and dismissing it must preserve focus and the
modal it belongs to, and must not undo the user's scroll. Animation must not
delay a necessary close or keep an invalid position on screen.

Equivalent overlays in one surface open in the same direction and alignment
unless the viewport forces a flip, and the same flip policy applies to all.

Prevents: A dropdown inside a parent with clipping overflow opened upward and
part of it was cut off behind the parent. Moving it out of the parent then
exposed follow-on failures: it detached from its trigger on scroll, extended
past the viewport, and opened in a different direction from equivalent
dropdowns.

Enforce with: For each added or changed overlay, open it with its trigger near
the edge of its scroll container and of the viewport; it must be fully visible
and clickable. Scroll the container and resize the window; it must stay
attached or close. Scroll the trigger out of view; it must close. Dismiss it;
focus must return to the trigger, an enclosing modal must stay open, and the
page must not scroll.
