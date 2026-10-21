# Architecture

RedScribe is a small desktop application with a strict split between the
storage/domain layer and the Tkinter user interface. The core uses only the
Python standard library.

## Layers

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Domain | `models.py`, `flags.py`, `fuzzy.py`, `utils.py` | Immutable data classes, flag detection, fuzzy ranking, formatting |
| Content | `markdown.py`, `highlight.py`, `templates.py`, `snippets.py` | Markdown parsing, code highlighting, note templates, command snippet library |
| Storage | `db.py` | SQLite schema, migrations, queries, settings, exports/imports support |
| Services | `importer.py`, `exporter.py`, `demo.py` | Markdown import, Markdown/HTML export, demo vault seeding |
| UI | `ui/*.py`, `app.py` | Tkinter widgets, dialogs, theming, window lifecycle |

Core modules never import Tkinter. The UI calls the `Vault` API and renders
returned models; it does not issue SQL directly.

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

1. `app.main()` parses CLI flags, resolves the vault path, and creates the Tk
   root. The root is hidden while the initial layout is built.
2. `MainWindow` reads persisted settings, configures ttk styles, constructs the
   header, sidebar, content stack, status bar, menus, and shortcuts, then opens
   the last note or the dashboard.
3. Editing updates the title/save state immediately, debounces preview rendering
   (250 ms), and debounces auto-save (1200 ms). Navigation and destructive
   operations force a save first. Split view can synchronize editor and preview
   scroll positions; the preference is persisted with the vault.
4. Theme or font changes save the open note, capture sash positions, rebuild
   the widget tree, and reopen the note in the new appearance.
5. Closing saves pending edits, geometry, and sash positions, then destroys the
   root. `app._run()` closes the vault in a `finally` block.

## Threading

All database and UI work runs on the Tk main thread. Operations are small enough
that no worker threads or queues are needed, which keeps SQLite connections
single-threaded and avoids cross-thread Tk calls.

## Testing

- `pytest -m "not gui"` runs core, storage, import/export, and service tests.
- `pytest -m gui` constructs the real window against a temporary vault. It needs
  a display; CI runs it under Xvfb.
- `ruff check`/`ruff format --check` enforce style, and `mypy src` checks the
  typed source tree.

## Extending

- Add a built-in snippet in `snippets.py`; the library is derived from that
  tuple and needs no schema change.
- Add a note template in `templates.py`; it appears in the new-note dialog.
- Add a vault operation as a `Vault` method with tests before wiring it into a
  dialog or menu.
- Add UI colors and fonts through `Palette`/`Theme` in `ui/theme.py` so both
  themes and the appearance rebuild stay consistent.
