## 2024-05-24 - Search inputs relying on placeholders
**Learning:** Found search and date inputs relying on placeholders or title attributes instead of ARIA labels.
**Action:** Adding explicit `aria-label` to these input fields.
## 2024-05-25 - Interactive overlays using semantic buttons
**Learning:** Found that the lightbox close control was an `<i>` tag, making it inaccessible to keyboard users and screen readers.
**Action:** Use a semantic `<button>` element with `aria-label` and native styling stripped out (`style="background: none; border: none; padding: 0;"`) for overlay controls to retain visual design while ensuring full keyboard accessibility.

## 2026-07-24 - Interactive Dynamic List Items
**Learning:** List items that function as buttons or links often lack keyboard support when built dynamically with JavaScript. Simply adding a click listener leaves out screen reader and keyboard-only users. Furthermore, numeric badges read in isolation (e.g., '14') are confusing to screen reader users.
**Action:** Always add `role="button"`, `tabindex="0"`, and a `keydown` listener (for Enter/Space) to interactive `<li>` elements. In addition, attach an `aria-label` and `title` to isolated numbers to provide context (e.g., '14 messages').
