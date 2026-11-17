# Changelog

All notable changes to RedScribe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- V2 platform kernel: schema v4 migration registry, entity event journal,
  idempotency key store, and request audit trail.
- Versioned API v2 with stable envelopes, error codes, request IDs, opaque
  cursors, ETags, canonical idempotent replay, and v1 compatibility dispatch.
- Additive frontend foundation: hash router, route registry, app shell, v2 API
  client, command registry, UI primitives including Toast, and `ui.css`.
- `scripts/loc_gate.py` and `scripts/branch_report.py` with CI jobs for LOC,
  test-line, v2 contract, and branch-mix gates.
- V2 architecture, API, branch playbook, and quality-gates documentation.

- Dependency-free motion system with System, Full, Subtle, and Off modes,
  persisted locally and exposed through the Motion lab.
- Spring page transitions, FLIP tree reordering, a sliding tree selection
  indicator, staggered entrances, and magnetic/tilt interactions.
- Animated dashboard counters, reading progress, copy-confetti, skeleton
  loading, toast presence exits, and origin-aware menus.
- Circular View Transitions theme switch with graceful fallback.
- Motion tokens, keyframes, reduced-motion auditing, and automated tests for
  spring math, preferences, and the accessibility kill switch.
- `docs/MOTION.md` with the motion map, performance rules, and manual QA list.
- Backlink panel in the note workspace: notes that link to the open note,
  resolved outlinks, and unresolved wikilinks (`[[Note Title]]`).
- Vault timeline (`Ctrl+Shift+T`): recent vault activity, newest first,
  filterable, with click-to-open notes.
- Tag system (2026-11 multi-agent pass): shared `lib/tags.ts` with dedupe,
  limits and normalization; reusable `TagInput` chip editor with vault-tag
  autocomplete in the properties and quick-capture dialogs.
- Tag explorer (palette → "Tag explorer"): live counts, search, sort;
  click a tag to filter the sidebar tree.
- Trash: "Restore all"; move-to-trash offers **Undo** in the toast.
- Status bar: reading time next to the word count.
- Frontend architecture: `Sidebar.tsx` → `TreeRow` / `SidebarRail` /
  `useSidebarResize`; `Dashboard.tsx` → `useDashboardData` (stable note
  signature) / `PulseStrip`; `NoteWorkspace.tsx` → `ToolButton` /
  `Breadcrumbs`; typed `lib/events.ts` replaces stringly-typed window
  events; `lib/api.ts` gained 10s `AbortController` timeouts and one
  transparent `save_content` retry; split bundles; drop unused `clsx`.
- Frontend tests: `scripts/test.mjs` now runs `motion.test.ts`,
  `tags.test.ts`, `tree.test.ts` (25 tests). pytest green: 218 passed.
- Frontend tooling: `docs/DESIGN_SYSTEM.md`, `docs/ACCESSIBILITY.md`
  (audit + measured contrast table), `docs/AGENT_DEVELOPMENT_REPORT.md`.

### Changed

- Legacy `--speed-*`/`--ease` CSS aliases forward to canonical
  `--motion-*` tokens; breakpoints normalized to `xs 420 / sm 560 / md 720 /
  lg 920 / xl 1180` and mirrored in `lib/breakpoints.ts`; hardcoded
  radius/size/gap/padding now use tokens; skeleton shimmer deduplicated;
  `--faint` raised to WCAG AA in both themes; focus rings standardized
  (2px, forced-colors support); destruction-safe cancel-first confirms;
  print drops app chrome.

### Fixed

- Graph API test seeded an empty vault and required non-empty nodes;
  backlinks route returns 404 `ApiError` for unknown ids; snippet search
  assertions match the intended fuzzy-ranking contract; modal close timer
  derives from `--motion-duration-base` at runtime (was 160 ms hard-coded
  vs 220 ms CSS exits); pytest basetemp moved off the full `C:` drive.

## [1.0.0] - 2026-10-21

### Added

- Local-first SQLite vault with hierarchical notes and folders.
- Drag-and-drop tree organization, keyboard reordering, and cycle-safe moves.
- Markdown editor with live syntax highlighting, line numbers, find/replace,
  auto-save, undo/redo, list and block-quote continuation, and keyboard
  formatting.
- Split preview with headings, lists, task lists, tables, quotes, links,
  syntax-highlighted code blocks, and optional synchronized scrolling.
- Full-text search (SQLite FTS5 with a LIKE fallback) and a fuzzy quick switch
  covering both notes and folders.
- CTF/pentest templates, note metadata, tags, flag detection, and a dashboard
  with recent/pinned notes, flags, tags, and import actions.
- Built-in snippet library with placeholder resolution plus custom snippets.
- Markdown and HTML export, whole-vault HTML report, vault backup, and
  Markdown import.
- Trash with restore and permanent delete, dark/light themes, and persisted
  window, sash, and preview preferences.
- Command-line options for vault path, demo seeding, theme, font size, and
  version reporting.
- Test suite with GUI smoke tests, strict typing across the full source tree,
  Ruff lint/format, and cross-platform CI.
