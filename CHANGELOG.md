# Changelog

All notable changes to RedScribe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
