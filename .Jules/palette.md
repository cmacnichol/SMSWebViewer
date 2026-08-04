## 2024-05-24 - Search inputs relying on placeholders
**Learning:** Found search and date inputs relying on placeholders or title attributes instead of ARIA labels.
**Action:** Adding explicit `aria-label` to these input fields.
## 2024-05-25 - Interactive overlays using semantic buttons
**Learning:** Found that the lightbox close control was an `<i>` tag, making it inaccessible to keyboard users and screen readers.
**Action:** Use a semantic `<button>` element with `aria-label` and native styling stripped out (`style="background: none; border: none; padding: 0;"`) for overlay controls to retain visual design while ensuring full keyboard accessibility.
## 2024-05-26 - Missing visual feedback on async forms
**Learning:** Discovered that critical forms like login, password change, and user creation didn't disable submit buttons or show loading states during async API requests, leading to potential duplicate submissions and poor user feedback.
**Action:** Always implement disabled states and explicit loading indicators (e.g., spinners) for form submit buttons that trigger async requests.
## 2024-05-27 - Keyboard navigation for dynamically created elements
**Learning:** Vanilla JS frontends that construct interactive list items and cards dynamically using template literals or `document.createElement()` often miss standard keyboard accessibility requirements (unlike typical semantic `<button>` elements).
**Action:** When dynamically creating interactive `<li>` or `<div>` items (e.g., in a contact list or search results), explicitly set `role="button"`, `tabindex="0"`, and attach a `keydown` listener for 'Enter' and 'Space' events to ensure full keyboard navigation. Also always add `aria-label` to dynamically created icon-only buttons.
