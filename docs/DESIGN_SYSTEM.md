# RedScribe design system

This document is the canonical reference for the Aurora interface's design
language. It describes the tokens, the themes, the motion system, the
accessibility contract, and the rules for using them. If you change a token,
change it here too.

Implementation lives in `frontend/src/styles/`.

| File | Role |
| --- | --- |
| `tokens.css` | Core tokens: type, spacing, radii, elevation, z-index, color theming, legacy aliases |
| `motion-tokens.css` | Canonical motion scale: durations, easings, distances, reduced-motion contract |
| `base.css` | Reset, focus ring, scrollbars, `sr-only`, keyframes, contrast/forced-colors support |
| `components.css` / `modals.css` / `workspace.css` / `layout.css` / `inspector.css` / `workbench.css` | Component styles |
| `motion-*.css` | Motion-aware refinements per surface |
| `ux-polish.css` | Final additive polish layer (caption, focus, chips) |

Loaded order is fixed in `styles/index.css`; later layers may refine, never
fork, the core tokens.

## Color

Two themes are supported via `data-theme` on `<html>`: `dark` (graphite, warm
accent) and `light` (warm paper). Both define the same semantic sets — never
reference raw hex values in component CSS; reference a semantic token so both
themes stay consistent.

### Semantic surfaces and text

| Token | Purpose |
| --- | --- |
| `--bg`, `--bg-deep`, `--bg-elev` | App background, recessed background, elevated background |
| `--sidebar-bg`, `--surface`, `--surface-2`, `--surface-3` | Sidebar, base cards, hover/raised, active/sunken |
| `--panel-bg`, `--editor-bg`, `--editor-gutter`, `--preview-bg` | Workspace panels |
| `--surface-glass(-strong)` | Translucent overlays |
| `--border`, `--border-strong`, `--border-accent` | Hairlines, emphasis hairlines, accent hairlines |
| `--text`, `--text-soft`, `--muted`, `--faint` | Primary, secondary, tertiary, quaternary text |
| `--accent`, `--accent-hover`, `--accent-2`, `--accent-soft`, `--accent-soft-2` | Brand accent and tints |
| `--blue/green/yellow/red/purple` (+`-soft`) | Status and flag-intel semantics |

**Contrast contract.** `--text`, `--text-soft`, and `--muted` measure at
4.5:1 or better against every surface they are designed for in both themes.
`--faint` is reserved for decorative or redundant glyphs; as of the A11y
redesign it also clears 4.5:1 on `--bg`, `--surface-2`, and `--surface-3`
(dark: `#848b99`; light: `#6b6357`). Do not introduce new text colors below
4.5:1 on their intended background. `@media (prefers-contrast: more)` raises
all tertiary hues a further step.

### Selection, focus, scroll

- `--selection` paints `::selection`.
- `--focus-ring-color`, `--focus-ring-width` (2px), offset 2px. One global
  `:focus-visible` outline in `base.css`; per-component rings use `box-shadow`
  with the same color.
- `--scroll-thumb`, `--scroll-thumb-hover` for themed scrollbars.

## Typography

| Family | Token | Usage |
| --- | --- | --- |
| UI text | `--font-ui` | All chrome: buttons, tree, toolbars, toasts |
| Display | `--font-display` | Hero numbers and dashboard mastheads |
| Mono | `--font-mono` | Editor, code, flags, kbd, timestamps |

Type scale (`--text-*`): `xs 10`, `sm 11`, `md 12`, `base 13`, `lg 14`,
`xl 16`, `2xl 18`, `3xl 21`, `4xl clamp(21px, 2.2vw, 27px)`. Line heights
`--leading-*` (1.2–1.7); tracking `--tracking-tight` (-0.02em) for display,
`--tracking-wide` (0.12em) for all-caps labels. Weights: normal 450,
medium 520, semibold 600, bold 650.

## Geometry

Spacing `--space-1…12` (4, 8, 12, 16, 20, 24, 32, 40, 48). Radii `--radius-xs
4 … --radius-xl 16` and `--radius-full`. Layout chrome: `--topbar-h 50px`,
`--statusbar-h 27px`, `--sidebar-w 272px`, `--sidebar-w-collapsed 80px`.
Z-index: `--z-topbar 20`, `--z-sash 30`, `--z-menu 60`, `--z-overlay 80`,
`--z-toast 100`.

`--touch-target: 44px` minimum hit area on coarse pointers (`@media
(pointer: coarse)` overrides key icon-button sizes).

### Breakpoints

Canonical values — CSS media queries cannot read custom properties, so both
`@media` rules and `useMediaQuery` calls must use these exact pixels (named
in JS as `BREAKPOINTS` from `frontend/src/lib/breakpoints.ts`):

| Token | px | Behavior |
| --- | --- | --- |
| `xs` | 420 | Single-column dialogs, compact phones |
| `sm` | 560 | Two-pane collapse, large phones |
| `md` | 720 | Tablets; split editor collapses; `useMediaQuery('md')` |
| `lg` | 920 | Inspector overlays workspace; sidebar becomes a drawer; `useMediaQuery('lg')` |
| `xl` | 1180 | Desktop density; splitter interactions; `useMediaQuery('xl')` |

Do not introduce other widths. Anything between `lg` and `xl` is `lg`
behavior; above `xl` is default.

## Motion

Canonical scale (motion-tokens.css). Durations: `instant 70ms`,
`fast 140ms`, `base 220ms`, `slow 340ms`, `slower 520ms`, `cinematic 760ms`.
Easings: `out cubic-bezier(0.22, 1, 0.36, 1)`, `soft (0.16, 1, 0.3, 1)`,
`in-out (0.65, 0, 0.35, 1)`, `spring cubic-bezier(0.34, 1.56, 0.64, 1)`.

The legacy tokens (`--speed-*`, `--ease`, `--ease-fast`, `--pressed-scale`)
are deprecated aliases for these and must not be used in new code. They are
retained because old CSS still references them; they carry the canonical
values.

Distances `--motion-distance(-sm)`, lift `--motion-lift`, press scale
`--motion-press-scale`, stagger step, tilt/ripple. All durations collapse to
0 (or 0.01ms) under `html[data-motion="off"]` and under
`prefers-reduced-motion` when the motion mode is `system`.

**Modal close** uses `modalExitDuration()` in `useUiStore.ts`, read from
`--motion-duration-base` at runtime so JS timers and CSS exits can never
drift apart. Toast exit timers are CSS-driven through `AnimatePresence`.

## Focus model

- Every interactive element gets `:focus-visible` ring: 2px solid
  `--focus-ring-color`, 2px offset, `--radius-sm` corner.
- Components that replace the outline must provide an equivalent
  `box-shadow: var(--ring)` treatment (tree rows, menu items, palette items,
  tabs).
- `@media (forced-colors: active)` remaps the ring to `CanvasText` and the
  selected states to `Highlight`/`HighlightText`; `forced-color-adjust: none`
  is applied only to selected rows/tabs.
- Destructive confirms receive initial focus on **Cancel**, not on the
  destructive button.

## Components contract

- **Buttons** — `.btn` variants `primary | ghost | subtle | danger | sm`;
  icon buttons `.icon-btn` (+`.sm`). Loading buttons keep their width.
- **Tree** — `role="tree"` with `treeitem` children; pinned note rows are
  `treeitem`s at `aria-level=1` with `aria-selected`.
- **Tabs** (inspector) — `role="tablist"`/`tab`/`tabpanel`, roving tabindex,
  `ArrowLeft/Right/Up/Down`, `Home`/`End` activate and focus.
- **Combobox** (quick switch) — input has `role="combobox"`,
  `aria-expanded`, `aria-controls`, `aria-activedescendant`,
  `aria-autocomplete="list"`; results container `role="listbox"`; each row
  `role="option"` with `aria-selected`; `Home`/`End` jump; `↑↓` cycle;
  `Esc` closes; a `role="status"` row announces loading.
- **Tooltips** — `role="tooltip"`, triggered by hover **and** focus,
  dismissed on `Esc`, scroll, and blur.
- **Toasts** — `role="status"` inside an `aria-live="polite"` stack.
- **Empty states** — `EmptyState` renders `role="status"` with explicit
  title/description/actions; loading states render `Skeleton` lines or
  `role="status"` rows (never a misleading "empty").
- **Modals** — trapped focus, labelled by `title`, `Esc`/backdrop close
  unless destructive; initial focus is the least-destructive control.

## Accessibility checklist for new UI

1. Color is never the only signal (icon, text, or shape accompanies it).
2. Contrast ≥ 4.5:1 for text, ≥ 3:1 for large text/graphics.
3. Everything reachable by keyboard; visible focus ring.
4. ARIA roles match interaction pattern (`tree`, `tablist`, `combobox`,
   `listbox`, `dialog`).
5. `Esc` closes the topmost layer; focus returns to the trigger.
6. Loading vs empty vs error are three distinct rendered states.
7. Motion respects `data-motion` and `prefers-reduced-motion`.
8. Touch targets ≥ 44×44 CSS px on coarse pointers.

## Adding new tokens

Add them once, in the layer they belong to (color/geometry → `tokens.css`,
motion → `motion-tokens.css`), give both themes a value if the token is
theme-dependent, document it here, and check both themes at 100% and 200%
zoom. Deprecated aliases may not gain new consumers.

## Contrast verification

Measured with the WCAG 2.x relative-luminance formula (2026-11). All text
pairs used by the dark graphite theme; light theme values in parentheses
where different.

| Foreground | Background | Contrast | Verdict |
| --- | --- | --- | --- |
| `--text #e8e9ed` (`#211d17`) | `--bg #0a0b0e` (`#f2efe9`) | 15.9:1 (13.9:1) | AAA |
| `--text-soft #b4b8c2` (`#4e483f`) | `--bg` (`--bg`) | 9.7:1 (8.9:1) | AAA |
| `--text-soft` | `--surface-2 #181c23` (`#f5f1e9`) | 8.6:1 (8.2:1) | AAA |
| `--muted #828a98` (`#746c61`) | `--bg` | 5.8:1 (4.6:1) | AA |
| `--muted` | `--surface-2` | 5.3:1 (4.9:1) | AA |
| `--muted` | `--surface-3 #20252f` (`#eae4d9`) | 4.7:1 (4.2:1 → `#544f45` in more-contrast) | AA / more-contrast |
| `--faint #848b99` (`#6b6357`) | `--bg` | 5.7:1 (5.2:1) | AA |
| `--faint` (redesign; was `#5f6673` = 3.4:1, `#9a9183` = 2.7:1) | `--surface-2` | 5.0:1 (5.3:1) | AA |
| `--faint` | `--surface-3` | 4.5:1 (4.7:1) | AA |
| `--accent #f05248` (`#ba3a30`) | `--bg` | 5.3:1 (5.6:1) | AA (text) |
| `--blue #78a7f7` (`#2d67c4`) | `--bg` | 8.2:1 (6.0:1) | AA |
| `--green #52c9a0` (`#167553`) | `--bg` | 10.1:1 (5.9:1) | AA |

Rules enforced by this redesign:

1. No text token below 4.5:1 on its documented surface in either theme.
2. `@media (prefers-contrast: more)` pushes every tertiary hue ≥ 4.5:1 even
   on `--surface-3`.
3. Decorative-only glyphs may use `--faint`; anything that carries meaning
   uses at least `--muted`.

## Redesign changelog (agent/ui-ux-redesign-01)

- Unified legacy `--speed-*`/`--ease`/`--pressed-scale` aliases onto the
  canonical `--motion-*` scale (aliases retained, deprecated).
- Raised `--faint` to AA in both themes (see table).
- Normalized every `@media` breakpoint to `xs 420 / sm 560 / md 720 / lg 920
  / xl 1180` and mirrored them in `lib/breakpoints.ts` (`useMediaQuery`
  callers).
- Normalized hardcoded `border-radius`, `font-size`, `gap`, and `padding`
  values to space/type/radius tokens across all stylesheets; added
  `--text-md` (12px) for the 12px step the old scale skipped.
- De-duplicated the skeleton shimmer (`.skel` and the container-level shimmer
  removed; `.skeleton`/`.skeleton-line` + `mx-shimmer` are canonical).
- Removed the duplicate `@keyframes shimmer`.
- Focus: destructive confirms focus Cancel, not the destructive action;
  `:focus-visible` rings standardized (2px, 2px offset); forced-colors and
  prefers-contrast modes now map borders, selection, and focus to system
  colors.
- Pointer: coarse-pointer hit areas raised to 44×44px (`--touch-target`).
- Keyboard: quick-switch is now a spec combobox/listbox (Home/End,
  aria-activedescendant); inspector tabs use roving tabindex with
  arrow/Home/End activation; pinned sidebar rows are `treeitem`s; tooltips
  show on focus and dismiss on Esc.
- State quality: Timeline and Graph show skeleton/`role=status` loading
  states instead of a misleading "empty" message; palette announces loading;
  status bar save state is a polite live region.
- JS timing derives from `--motion-duration-base` (no more 160ms vs 220ms
  modal-exit drift).
