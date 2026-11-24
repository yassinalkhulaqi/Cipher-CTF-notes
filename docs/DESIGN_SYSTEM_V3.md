# Design System v3

## Foundations

`frontend/src/styles/tokens-v3.css` defines spacing, type, radius, elevation,
semantic colors, entity-kind colors, motion durations, and density modes. Every
feature imports this file; no feature redefines a foundation token.

## Component contract

Each V3 component accepts:

- a stable `data-*` attribute for testing and state styling;
- explicit `aria-*` labels for interactive controls;
- keyboard activation without a pointer;
- visible `:focus-visible` outlines using `--v3-focus`;
- reduced-motion behavior that keeps content usable;
- both light and dark themes through semantic tokens.

## Shared primitives (B00)

- `V3Panel` — titled surface with a kind-colored accent rail, optional actions,
  and comfortable/compact density.
- `V3Stat` — metric tile with label, tabular value, hint, and tone.
- `V3Client` — typed envelope client with request IDs, ETags, pagination, and
  typed errors.
- feature/command registries — additive, ordered, searchable.

## Density

`data-density="compact"` targets dense tables and command lists;
`data-density="comfortable"` is the default for reading surfaces. Row heights
are driven by `--v3-row-height`.

## Kind colors

note, folder, target, finding, evidence, playbook, run, report, section,
activity, extension, snippet each have a semantic color token. Unknown kinds
fall back to `--v3-kind-default` so early merges never render blank.

## Motion

`--v3-motion-fast/normal/slow` and `--v3-ease`. Under
`prefers-reduced-motion: reduce`, transitions are removed without hiding
content. B12 unifies motion preferences with the V2 motion system.
