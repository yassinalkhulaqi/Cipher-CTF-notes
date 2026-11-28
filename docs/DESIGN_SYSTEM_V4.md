# RedScribe v4 Design System

**Token source:** `frontend/src/styles/tokens-v4.css`
**Rule:** features consume tokens; they never redefine them.

## 1. Principles

1. **Calm by default.** Warm paper tones in light mode, graphite in dark mode.
2. **Dense but readable.** Three density modes: compact, default, comfortable.
3. **Visible focus.** Every interactive element uses `--v4-focus-ring`.
4. **Reduced motion is first-class.** `prefers-reduced-motion` zeroes all durations.
5. **Localized.** RTL is a data attribute, not a stylesheet fork.

## 2. Token groups

| Group | Examples |
| --- | --- |
| Surfaces | `--v4-bg`, `--v4-surface`, `--v4-surface-2`, `--v4-surface-3` |
| Text | `--v4-text`, `--v4-text-muted`, `--v4-text-faint` |
| Semantic | `--v4-accent`, `--v4-success`, `--v4-warning`, `--v4-danger`, `--v4-info` |
| Spacing | `--v4-space-1` … `--v4-space-16` (4px base) |
| Type | `--v4-text-xs` … `--v4-text-2xl`; `--v4-font-ui`, `--v4-font-mono` |
| Elevation | `--v4-shadow-sm`, `--v4-shadow-md`, `--v4-shadow-lg` |
| Radius | `--v4-radius-sm` … `--v4-radius-pill` |
| Motion | `--v4-duration-fast` … `--v4-duration-slow`, `--v4-ease` |
| Layout | `--v4-header-h`, `--v4-sidebar-w`, `--v4-content-max`, `--v4-density-row` |

## 3. Themes

- `data-v4-theme="light"` (default): warm paper.
- `data-v4-theme="graphite"`: dark graphite.
- `data-v4-theme="system"`: follows `prefers-color-scheme`, resolved by `applyPreference`.

## 4. Density modes

- `compact`: 28px rows, tighter spacing.
- `default`: 36px rows.
- `comfortable`: 44px rows, looser spacing.

## 5. Components

| Class | Purpose |
| --- | --- |
| `.v4-panel` | Card surface with border and subtle shadow |
| `.v4-chip` / `.v4-chip--accent` | Metadata pills |
| `.v4-btn` / `.v4-btn--primary` | Buttons |
| `.v4-focus-ring` | Visible keyboard focus |
| `.v4-scroll` | Thin themed scrollbars |
| `.v4-empty` | Empty-state layout |
| `.v4-sr-only` | Screen-reader-only text |

## 6. Shell

The shell is a two-column grid: a collapsible sidebar (`--v4-sidebar-w`) and a
main region with header, content, and footer. Below 860px the sidebar becomes an
off-canvas drawer toggled by `v4-shell--mobile-open`.

## 7. Motion policy

`Preferences.motion` maps to three document states:

- `full`: all transitions enabled.
- `subtle`: opacity-only transitions.
- `off`: zero durations.

The `prefers-reduced-motion` media query always wins by zeroing durations in CSS.

## 8. Accessibility checklist

- Every control has an accessible name.
- Focus order matches visual order.
- Color is never the only signal; pair it with text or shape.
- RTL layouts mirror navigation and paddings through CSS logical properties.
- Status changes are announced through an aria-live region.
