# Architecture

RedScribe is a small desktop application with a strict split between the
storage/domain layer and the web-based user interface. The core uses only the
Python standard library.

## Layers

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Domain | `models.py`, `flags.py`, `fuzzy.py`, `utils.py` | Immutable data classes, flag detection, fuzzy ranking, formatting |
| Content | `markdown.py`, `highlight.py`, `templates.py`, `snippets.py` | Markdown parsing, code highlighting, note templates, command snippet library |
| Storage | `db.py` | SQLite schema, migrations, queries, settings, exports/imports support |
| Services | `importer.py`, `exporter.py`, `demo.py`, `graph.py`, `flag_intel.py` | Markdown import, Markdown/HTML export, demo vault seeding, vault knowledge graph and backlinks/timeline, flag format registry and insights |
| UI | `ui/web/`, `app.py` | Localhost HTTP API + bundled React web frontend (native webview or browser) |

Core modules never import the desktop UI layer. The web frontend calls the
same `Vault` API over localhost HTTP and renders returned models; it does not
issue SQL directly.

## Data model

A vault is one SQLite file containing:

- `nodes` -- one table for both folders and notes, linked by `parent_id`.
  Notes carry Markdown content, comma-separated tags, target, status,
  difficulty, flag, pin state, and timestamps.
- `snippets` -- user-created command snippets. Built-in snippets live in
  `snippets.py` and are not duplicated into the database.
- `settings` -- a key/value table for window geometry, theme, font size, view
  mode, and the last opened note.
- `nodes_fts` -- an FTS5 external-content index over title, content, and tags,
  kept current by insert/update/delete triggers. If FTS5 is unavailable, the
  vault disables the index and search falls back to `LIKE`.

Deleting a note moves it to the trash by setting `deleted_at`; restore clears
the timestamp. Permanent deletion removes the row and cascades to descendants.

The schema version is stored in `PRAGMA user_version`. A vault created by a
newer schema is rejected instead of being modified.

## Application flow

1. `app.main()` parses CLI flags, resolves the vault path, and hands off to
   `redscribe.ui.web.launcher.run`, which starts the local HTTP server and
   opens the bundled React frontend in a native webview or the system browser.
2. The launcher starts the threaded API server on `127.0.0.1`, seeds the demo
   vault when empty, and serves the SPA shell and assets from the wheel.
3. The web frontend loads the tree, opens the last note or the dashboard, and
   saves content through the JSON API; the launcher serializes vault access
   through a single-worker executor.
4. Theme or font overrides are passed to the API and persisted via settings.
5. Closing shuts the server down and closes the vault.

## Threading

The local API server is threaded, but all database work funnels through a
single-worker executor inside the launcher, which keeps SQLite connections
single-threaded and avoids cross-thread writes.

## Testing

- `pytest` runs core, storage, import/export, and service tests.
- `ruff check`/`ruff format --check` enforce style, and `mypy src` checks the
  typed source tree.

## Extending

- Add a built-in snippet in `snippets.py`; the library is derived from that
  tuple and needs no schema change.
- Add a note template in `templates.py`; it appears in the new-note dialog.
- Add a vault operation as a `Vault` method with tests before wiring it into a
  dialog or menu.
- Add UI colors through the design tokens in `frontend/src/styles/` so both
  themes stay consistent.
