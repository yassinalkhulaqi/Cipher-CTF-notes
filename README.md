# RedScribe

**A lightweight, local-first notebook for CTFs, pentests, and security research.**

RedScribe is a desktop notes app with a CherryTree-style tree, a focused Markdown
editor, live preview, full-text search, CTF flag tracking, target metadata, and a
searchable library of offensive-security command snippets. The default frontend
is **Aurora**, a bundled React interface served locally by Python and opened in a
native webview or browser. One SQLite vault. No accounts. No telemetry. No
network calls.

![RedScribe editor with the tree, Markdown source, and live preview](docs/demo.png)

## Highlights

- **Fast capture.** Hierarchical folders and notes, drag-and-drop organizing,
  instant fuzzy jump to notes or folders with `Ctrl+P`, full-text search with
  `Ctrl+Shift+F`, and auto-save.
- **Built for security work.** Templates for CTF challenges, host recon, web
  assessments, findings, and engagement logs. Notes carry a target, status,
  difficulty, tags, and a captured flag.
- **Useful snippets.** More than 70 built-in commands for recon, web, Active
  Directory, credentials, shells, privesc, pivoting, and CTF tooling. Copy with
  placeholders filled from the current note.
- **Readable output.** Markdown editor with syntax highlighting and a split
  preview with code highlighting and optional synchronized scrolling. Export a
  note to Markdown or HTML, or export the whole vault as a browsable HTML report.
- **Aurora interface.** A responsive React workspace with a real-data research
  dashboard, command palette, focused editor, find and replace, live preview,
  snippet library, and warm light or graphite dark themes. Runs in a native
  webview or any modern browser.
- **Motion that explains.** Spring-based page and tree transitions, a sliding
  selection indicator, tilt-aware dashboard panels, animated counters, a reading
  progress bar, view-transition theme changes, and a Motion lab with System,
  Full, Subtle, and Off modes.
- **Small and portable.** The entire vault is one file that you can back up,
  sync, or move. Frontend assets are bundled into the wheel.

## Install

```bash
python -m pip install ".[web]"   # native window (pywebview)
redscribe
```

Without the `web` extra RedScribe falls back to the default browser. Or run it
from the source tree:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
python -m pip install -e ".[dev]"
python -m redscribe --demo
```

Linux users need Tkinter: `sudo apt-get install python3-tk`.

## Quick start

1. Launch RedScribe. The first-run dashboard can load the demo vault.
2. Create a **CTF challenge** or **Host recon** note and fill in the target.
3. Write notes in Markdown. Press `Ctrl+E` to cycle editor, split, and preview,
   or `Ctrl+F` / `Ctrl+H` to find and replace inside the note.
4. Press `Ctrl+P` to jump anywhere, or `Ctrl+Shift+S` for snippets.
5. Export a single note or the whole vault from the **File** menu.

The default vault lives in your OS data directory (`%APPDATA%\RedScribe` on
Windows, `~/Library/Application Support/RedScribe` on macOS, and
`~/.local/share/redscribe` on Linux). Override it with `--vault PATH`.

## Shortcuts

| Shortcut                | Action                               |
| ----------------------- | ------------------------------------ |
| `Ctrl+N`                | New note (last template)             |
| `Ctrl+Shift+N`          | New folder                           |
| `Ctrl+P`                | Quick switch                         |
| `Ctrl+Shift+F`          | Full-text search                     |
| `Ctrl+Shift+S`          | Snippets                             |
| `Ctrl+Shift+D`          | Dashboard                            |
| `Ctrl+Shift+P`          | Pin or unpin the current note        |
| `Ctrl+E`                | Cycle editor / split / preview       |
| `Ctrl+S`                | Save now                             |
| `Ctrl+,`                | Settings                             |
| `Ctrl+F` / `Ctrl+H`     | Find / replace                       |
| `F2`                    | Note properties                      |
| `Delete`                | Move the selected tree item to trash |
| `Ctrl+Up` / `Ctrl+Down` | Reorder the selected tree item       |
| `F1`                    | All shortcuts                        |

When the editor has focus: `Ctrl+B` bold, `Ctrl+I` italic, `Ctrl+K`
inline code, `Ctrl+Shift+X` strikethrough, `Tab` / `Shift+Tab` indent, and
`Ctrl+Z` / `Ctrl+Y` undo and redo. The full list is in
[docs/SHORTCUTS.md](docs/SHORTCUTS.md).

## Development

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest -m "not gui"
```

Frontend work lives in `frontend/` and uses Node 20+:

```bash
cd frontend
npm install
npm run dev       # watch and rebuild the Python static bundle
npm test          # TypeScript typecheck
npm run build     # production bundle
```

The motion engine is dependency-free. Modes, tokens, primitives, performance
rules, and the accessibility contract are documented in
[docs/MOTION.md](docs/MOTION.md).

The GUI smoke test runs with `python -m pytest -m gui` on a machine with a
display. Architecture notes live in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); the Aurora UI notes live in
[docs/AURORA.md](docs/AURORA.md).

Command-line options:

```bash
redscribe --vault PATH     # use a specific SQLite vault
redscribe --demo           # seed example notes into an empty vault
redscribe --ui browser     # browser tab instead of a native window
redscribe --ui tk          # classic Tkinter interface
redscribe --port 8765      # fixed local web port (0 = choose one)
redscribe --no-open        # start the web server without opening a browser
redscribe --theme light    # override the stored theme
redscribe --font-size 13   # override the stored UI font size
redscribe --version
```

## Authorized use only

RedScribe is for CTF competitions, labs, and engagements where you have explicit
written permission. The snippets are reference material. You are responsible
for how you use them.

MIT licensed.
