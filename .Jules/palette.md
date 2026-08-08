## 2024-05-24 - Search inputs relying on placeholders
**Learning:** Found search and date inputs relying on placeholders or title attributes instead of ARIA labels.
**Action:** Adding explicit `aria-label` to these input fields.
## 2024-05-25 - Interactive overlays using semantic buttons
**Learning:** Found that the lightbox close control was an `<i>` tag, making it inaccessible to keyboard users and screen readers.
**Action:** Use a semantic `<button>` element with `aria-label` and native styling stripped out (`style="background: none; border: none; padding: 0;"`) for overlay controls to retain visual design while ensuring full keyboard accessibility.
## 2024-05-26 - Missing visual feedback on async forms
**Learning:** Discovered that critical forms like login, password change, and user creation didn't disable submit buttons or show loading states during async API requests, leading to potential duplicate submissions and poor user feedback.
**Action:** Always implement disabled states and explicit loading indicators (e.g., spinners) for form submit buttons that trigger async requests.
## 2024-05-27 - Keyboard accessibility for dynamically created interactive elements
**Learning:** Dynamically created interactive elements (like `<li>` tags used as list items) lack native keyboard support, which prevents users from navigating and interacting via keyboard.
**Action:** Explicitly set `role="button"` and `tabindex="0"`, and add a `keydown` listener for 'Enter' and 'Space' to mimic the `click` event behavior.
