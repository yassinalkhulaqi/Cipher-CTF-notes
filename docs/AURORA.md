# Aurora web interface

RedScribe ships with a React and TypeScript frontend served by the local Python
HTTP server. The Python vault, SQLite storage, search index, templates, and
snippets remain the source of truth; the browser or pywebview window is a thin
client over the existing JSON API.

## Architecture

- `frontend/src` contains the React application, Zustand stores, hooks, and CSS.
- `frontend/scripts/build.mjs` bundles the app into
  `src/redscribe/ui/web/static` with esbuild.
- `src/redscribe/ui/web/server.py` serves the SPA shell, hashed assets, downloads,
  and the local JSON API on `127.0.0.1`.
- `src/redscribe/ui/web/launcher.py` opens the server in pywebview or the default
  browser and supports `--port` and `--no-open`.

The frontend never talks to the network. The server binds to loopback, refuses
cross-origin use, sends `nosniff`, and applies a strict content-security policy.

## Development

```bash
cd frontend
npm install
npm run dev        # esbuild watch + Python static output
npm test           # TypeScript typecheck
npm run build      # production bundle + typecheck
```

Run the desktop shell from the repository root:

```bash
python -m redscribe --demo --ui window
python -m redscribe --ui browser --port 8765
python -m redscribe --ui browser --no-open
```

The browser-only workflow is useful for UI work: start the server with
`--no-open`, then open the printed loopback URL in a browser.

## Design notes

The Aurora direction uses graphite and warm paper themes, a crimson accent,
compact responsive chrome, restrained surfaces, a monospace source editor, and
minimal motion. The dashboard reads directly from the vault API: recent work,
captured flags, active and pinned notes, targets, tags, and starter templates.
The editor renders a syntax-highlighted overlay behind a transparent textarea
with a plain mode for composition, large notes, and accessibility.

The research workbench adds a collapsible icon rail for workspace navigation, a
note inspector for outline, links, and properties, a graph selection panel, and
a flag intelligence view for captured values, format shape, duplicates, and
gaps. Flag labels describe format shape only; they are not validation.

Tokens live in `frontend/src/styles/tokens.css`; layout, workspace, modal, and
feedback styles are split into focused stylesheets imported by
`frontend/src/styles/index.css`. The workbench additions live in
`inspector.css`, `flag-intel.css`, and `workbench.css`.
