## 2024-05-24 - Search inputs relying on placeholders
**Learning:** Found search and date inputs relying on placeholders or title attributes instead of ARIA labels.
**Action:** Adding explicit `aria-label` to these input fields.
## 2024-05-25 - Interactive overlays using semantic buttons
**Learning:** Found that the lightbox close control was an `<i>` tag, making it inaccessible to keyboard users and screen readers.
**Action:** Use a semantic `<button>` element with `aria-label` and native styling stripped out (`style="background: none; border: none; padding: 0;"`) for overlay controls to retain visual design while ensuring full keyboard accessibility.
## 2024-05-26 - Missing visual feedback on async forms
**Learning:** Discovered that critical forms like login, password change, and user creation didn't disable submit buttons or show loading states during async API requests, leading to potential duplicate submissions and poor user feedback.
**Action:** Always implement disabled states and explicit loading indicators (e.g., spinners) for form submit buttons that trigger async requests.
## 2026-07-26 - Dynamic List Item Accessibility
**Learning:** When generating interactive list items or cards dynamically via JavaScript (like the contact list or search results), they lack keyboard accessibility by default. It is not enough to just add a click handler.
**Action:** Always add `role="button"` (or appropriate role) and `tabindex="0"` when creating interactive non-button/link elements. Also ensure you add a `keydown` listener to handle 'Enter' or 'Space' and provide a clear `:focus-visible` style so keyboard users know which element has focus.
