## 2024-05-24 - Search inputs relying on placeholders
**Learning:** Found search and date inputs relying on placeholders or title attributes instead of ARIA labels.
**Action:** Adding explicit `aria-label` to these input fields.
## 2024-05-25 - Interactive overlays using semantic buttons
**Learning:** Found that the lightbox close control was an `<i>` tag, making it inaccessible to keyboard users and screen readers.
**Action:** Use a semantic `<button>` element with `aria-label` and native styling stripped out (`style="background: none; border: none; padding: 0;"`) for overlay controls to retain visual design while ensuring full keyboard accessibility.
## 2024-05-26 - Missing visual feedback on async forms
**Learning:** Discovered that critical forms like login, password change, and user creation didn't disable submit buttons or show loading states during async API requests, leading to potential duplicate submissions and poor user feedback.
**Action:** Always implement disabled states and explicit loading indicators (e.g., spinners) for form submit buttons that trigger async requests.

## 2024-05-24 - Interactive List Items
**Learning:** When using non-interactive elements like `<li>` or `<div>` as buttons or links in custom UI components (like the contact list), mouse events alone exclude keyboard and screen reader users.
**Action:** Always follow the "interactive element checklist" for non-native buttons: add `tabindex="0"`, `role="button"`, an appropriate `aria-label`, a keydown event listener for Enter/Space, and `:focus-visible` styling for visual feedback.
