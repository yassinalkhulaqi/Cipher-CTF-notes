# Changelog

All notable changes to RedScribe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-21

### Added

- Local-first SQLite vault with hierarchical notes and folders.
- Markdown editor with live syntax highlighting, line numbers, find/replace,
  auto-save, undo/redo, list continuation, and keyboard formatting.
- Split preview with headings, lists, task lists, tables, quotes, links, and
  syntax-highlighted code blocks.
- Full-text search (SQLite FTS5 with a LIKE fallback) and fuzzy quick switch.
- CTF/pentest templates, note metadata, tags, flag detection, and dashboard.
- Built-in snippet library with placeholder resolution plus custom snippets.
- Markdown and HTML export, whole-vault HTML report, vault backup, and
  Markdown import.
- Trash with restore and permanent delete, dark/light themes, and persisted
  window and sash state.
- Command-line options for vault path, demo seeding, theme, font size, and
  version reporting.
- Dashboard with recent/pinned notes, flags, tags, and quick actions.
- Test suite with GUI smoke tests, strict typing for the core, Ruff
  lint/format, and cross-platform CI.
