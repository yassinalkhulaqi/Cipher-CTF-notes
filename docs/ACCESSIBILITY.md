# Accessibility

RedScribe aims for WCAG 2.1 AA in both themes and on both keyboard and
pointer. This document records the contract (what is enforced, where), the
audit that shipped with the Aurora redesign, and the known limitations that
remain. It is a living document — update it when adding patterns.

## What is enforced

| Area | Contract | Where |
| --- | --- | --- |
| Contrast | All text tokens ≥ 4.5:1 on their documented surfaces in both themes; `prefers-contrast: more` steps every tertiary hue up a further tier | `styles/tokens.css`, `styles/base.css`, `docs/DESIGN_SYSTEM.md` |
| Focus | Single 2px `--focus-ring-color` outline, 2px offset, or an inset equivalent; SVG nodes ring by stroke | `styles/base.css`, `components.css` |
| Forced colors | System colors re-skin borders, selection, tabs, and focus; `forced-color-adjust: none` only on selected rows/tabs | `styles/base.css` |
| Motion | `data-motion="off"` or `prefers-reduced-motion` (system mode) collapses durations to 0.01ms; modal close timer is read from the `--motion-duration-base` token at runtime | `styles/motion-tokens.css`, `store/useUiStore.ts` |
| Keyboard | Tree (`tree`/`treeitem`, arrow navigation), menu (role=menu + roving focus), palette (combobox/listbox), inspector tabs (roving tabindex), `Esc` closes the topmost layer, `Tab` cycles dialog focus | components; `useFocusTrap` restores focus |
| Touch | ≥ 44×44px hit targets on coarse pointers | `styles/base.css` (`--touch-target`) |
| Landmarks | `<main id="main-content">`, skip link as first focusable element, `role=status` live regions for save state and toasts | `App.tsx`, `StatusBar.tsx`, `ToastStack.tsx` |

## Interaction-pattern reference

- **Quick switch (Ctrl+P)** — `role="combobox"` input; `aria-expanded`,
  `aria-controls`, `aria-activedescendant`,
  `aria-autocomplete="list"`; results in `role="listbox"`; rows are
  `role="option"` with `aria-selected`. `↑↓` move (wrapping), `Home`/`End`
  jump to the first/last option, `Enter` activates, `Esc` closes.
  A `role="status"` row announces loading results.
- **Inspector tabs** — `role="tablist"`/`tab`/`tabpanel`; roving tabindex
  (active tab `tabindex=0`, others `-1`); `ArrowLeft/Right/Up/Down` cycle,
  `Home`/`End` jump; activation is automatic on focus (APG
  "tabs with automatic activation").
- **Sidebar tree** — `role="tree"`; notes and folders are `treeitem`s with
  `aria-level`, `aria-selected`, `aria-expanded` (folders). Pinned-note rows
  are also `treeitem`s (`aria-level=1`).
- **Modals** — labelled via `title`, focus trapped, least-destructive action
  receives initial focus (destructive confirms focus **Cancel**), `Esc` /
  backdrop close, focus returns to the trigger element on unmount.
- **Tooltips** — `role="tooltip"`; shown on hover and on focus of the
  tooltip owner; hidden on `Esc`, `scroll`, blur, or mouse-out.
- **Empty vs loading vs error** — every async surface renders one of three
  distinct states. Loading uses skeleton lines or a `role="status"` row;
  empty uses the shared `EmptyState` (`role="status"`); errors render inline
  with an actionable message.

## 2026-11 redesign audit — before / after

| Finding | Before | After |
| --- | --- | --- |
| `--faint` quaternary text | 3.4:1 (dark) / 2.7:1 (light) on `--bg` — fails AA | 5.7:1 / 5.2:1 — AA |
| Modal close timer | Hard-coded 160ms while CSS exits ran 220ms (truncated exit; 160ms lag with motion off) | Reads `--motion-duration-base` at runtime |
| Destructive confirm initial focus | Landed on the destructive button | Lands on Cancel |
| Confirm action failure | Unhandled promise rejection, silent | `role="status"` error toast |
| Quick switch semantics | `<input>` + buttons, no combobox/listbox roles | Full combobox pattern, Home/End support |
| Inspector tabs | No roving tabindex, no arrow-key support | APG automatic-activation tabs with roving tabindex |
| Pinned sidebar rows | Plain `<button>` inside `role="tree"` | `treeitem`, `aria-selected`, `tabIndex` |
| Tooltips | Mouse-only | Focus + hover, dismissed by Esc/scroll/blur |
| Timeline modal | "No activity yet" while loading | Skeleton rows + `role="status"` |
| Graph modal | "No notes match the filter" while loading | `role="status"` canvas placeholder + skeleton rows |
| Command palette loading | Silent until results land | `aria-busy` listbox + `role="status"` loading row |
| Save indicator | Not announced | `role="status"` + `aria-live="polite"` |
| Focus ring on custom widgets | Mixed `box-shadow` vs outline, no SVG story | Unified 2px ring, SVG graph nodes ring by stroke |
| Coarse pointers | Icons at 30px (below HIG/AA-ish guidance) | 44×44px hit areas on small buttons |
| High contrast | None | `prefers-contrast: more` token boost + `forced-colors: active` remap |
| Printing | Chrome reprinted with note | `@media print` prints note content only |

Contrast ratios verified with the WCAG 2.x relative-luminance formula; see
`docs/DESIGN_SYSTEM.md#contrast-verification` for the full table.

## Known gaps (tracked for follow-up)

1. **Graph canvas** — SVG `<g role="button">` nodes are reachable, but the
   force-layout is not announced structurally (no list alternative). A
   tabular "connections" view is the planned fallback.
2. **Markdown preview** — server-escaped HTML is injected with
   `dangerouslySetInnerHTML`; safe today (allowlist sanitizer on the server)
   but lacks defense-in-depth client-side sanitization. Tracked.
3. **Motion lab** — hidden behind the palette in production builds; should
   ship behind a dev-only flag.
4. **Automated tests** — component-level a11y tests (axe) are planned in the
   QA branch; today the suite covers motion math and preferences only.
5. **Locale** — the UI is English-only; `lang` attributes and `dir` handling
   are correct, but translated copy does not exist yet.

## How to test

1. `npm run typecheck` — types.
2. Manual: Tab through the whole shell with no mouse; activate the quick
   switch with `Ctrl+P`, arrow to a note, `Enter`.
3. DevTools → Rendering → emulate `prefers-reduced-motion: reduce` and
   `prefers-contrast: more`; verify no truncation of modal exits.
4. Lighthouse a11y audit on the built app (target ≥ 95).
5. With the QA branch merged: `npm test` runs the axe-scanned component
   suite.

## V3 refinement (B12)

V3 adds WCAG 2.2 audits, automated contrast repair, six additional locale
catalogs, RTL pane metadata, a complete keyboard map, and synchronized
preferences with one unified theme/motion control. See
`docs/v3/a11y-i18n.md` for the contracts, routes, components, and gates.
