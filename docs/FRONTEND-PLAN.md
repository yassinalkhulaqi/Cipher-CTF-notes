# RedScribe — Front-End Plan

Owner: yassinalkhulaqi
Last updated: 2026-11-17
Status: Active — front-end-first delivery

## Vision

RedScribe should feel like a precision instrument for security work: calm chrome,
a reading experience that disappears into the note, and feedback that explains
what the interface is doing without demanding attention.

The front end owns perception. Every animation, color, type scale, focus ring, and
empty state is a product decision that must survive the dark graphite, light paper,
and reduced-motion contracts already in place.

## Principles

1. Ship perceptual changes front end first; back end only when data or domain
   truth is missing.
2. Design tokens are the single source of truth. New colors, radii, and motion
   values ship as tokens, never raw literals in components.
3. Motion is expressive but budgeted. Duration and easing come from the motion
   tokens; reduced motion and `prefers-contrast` override everything.
4. Accessibility is part of the component contract, not a follow-up.
5. Local-first means the front end never assumes network. Rendered state comes
   from the vault API or ephemeral UI state only.
6. Small surfaces: a feature is a component plus its lib plus its stylesheet plus
   its tests, shipped as one branch.

## Phases

### Phase 0 — Front-end foundation

- Keep tokens as the single source of truth; split shared component styles from
  feature styles.
- Finish design-system inventory: buttons, inputs, menus, modals, toasts,
  tooltips, workbench chrome.

### Phase 1 — Reading and writing experience (started)

- Reading view with user-controlled measure, type scale, leading, and theme.
- Editor telemetry: live word count, reading time, autosave state.
- Distraction-free writing surfaces.

### Phase 2 — Intelligence surfaces

- Dashboard momentum and flag insight widgets.
- Search facets (tags, status, difficulty, source).
- Vault stats and grouping.

### Phase 3 — Velocity

- Quick capture templates and flow.
- Command palette history and frecency.
- Keyboard customization.

### Phase 4 — Craft

- Theme studio with live preview.
- Motion presets and micro-interactions.
- Export presentation (HTML/PDF print).

## Milestones

| Milestone | Scope | Branch |
| --- | --- | --- |
| M1 Reader | Reading view, editor telemetry | `feat/aurora-reading-view` |
| M2 Momentum | Dashboard momentum chart | `feat/aurora-momentum-dashboard` |
| M3 Search | Faceted search | `feat/aurora-search-facets` |
| M4 Capture | Quick capture templates | `feat/aurora-capture-templates` |
| M5 Themes | Theme studio | `feat/aurora-theme-studio` |
| M6 Notifications | Notification center | `feat/aurora-notifications` |

## Quality bar

- `cd frontend && npm run typecheck`
- `npm test`
- `npm run format:check`

## Delivery format

Each milestone ships as its own branch off `main`, one commit per branch, named
`feat/<slug>`, with component, lib, stylesheet, and tests in that branch.
