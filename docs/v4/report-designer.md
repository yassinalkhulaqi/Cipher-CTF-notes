# v4 Report Designer — `docs/v4/report-designer.md`

The v4 report designer turns engagement data into visual, client-ready reports.
It is a data-only feature: layouts, themes, pagination and exports are plain
values, with no shell commands, file reads or network calls in the domain code.

## Scope and placement

- Python package: `src/redscribe/v4/report_designer/`
- Tests: `tests/v4_report_designer/`
- Frontend: `frontend/src/features/report-designer/v4/` (a v4 subdirectory
  avoids colliding with the existing v3 `report-designer` feature)
- Frontend tests: `frontend/scripts/v4-report-designer.test.ts`
- Test manifest: `frontend/scripts/test-suites/v4-07.json`

## Data model (`types.py`)

| Type | Purpose |
| --- | --- |
| `PageSize` | `A4`, `LETTER`, `A5` with physical dimensions in mm |
| `Orientation` | `PORTRAIT` / `LANDSCAPE`, applies dimension swapping |
| `SectionKind` | `COVER`, `TOC`, `FINDINGS`, `EVIDENCE`, `APPENDIX` |
| `ReportTheme` | Named theme with optional parent and partial patches |
| `ThemeColors` / `ThemeFonts` / `ThemeMargins` | Partial override patches, validated and mergeable |
| `ResolvedTheme` | Fully materialized theme with CSS variables and print area |
| `ReportEntry` | One wrapped line-level item (title, detail, level, ref) |
| `ReportSection` | Titled group of entries with `page_break_before` |
| `ReportLayout` | Complete report definition: id, title, theme, geometry, sections |
| `PaginatedPage` | Page number, originating section, lines, title |
| `ExportFormat` | `HTML` / `MARKDOWN`, extension and MIME type |

Every type validates input, normalizes whitespace and supports `to_dict()` /
`from_dict()` round-trips. Bounds prevent oversized payloads crossing the API
boundary; identifiers follow `^[A-Za-z][A-Za-z0-9_.:-]{0,63}$`.

## Theme inheritance (`service.py`)

`ThemeResolver` registers the `base` theme plus five built-ins:

```
base
├── classic ── modern ── ink
├── compact ── client
```

Each child stores only overrides. `resolve(name)` follows the parent chain,
detects cycles, and merges colors, fonts, margins, header and footer from root
to leaf. Results are cached until a theme is registered or the cache is
cleared. `ResolvedTheme.css_variables()` yields `--report-*` properties for the
HTML exporter; `page_area_mm(size, orientation)` computes the printable area.

A custom theme is just data:

```python
resolver.register(
    ReportTheme(
        name="client-dark",
        parent="ink",
        colors=ThemeColors(primary="#2f5d8a"),
        margins=ThemeMargins(top=12),
    )
)
resolved = resolver.resolve("client-dark")
```

## Pagination

`PaginationConfig` fixes `lines_per_page`, `line_width` and `section_gap`.
`PaginationEngine`:

1. renders a section heading and underline;
2. wraps each entry title and detail to the configured width, preserving
   indentation by entry level;
3. honors `page_break_before` by flushing the current page;
4. flushes automatically when a page reaches its line budget;
5. numbers pages from one and tags each with the section that opened it.

The engine is deterministic: the same layout always produces the same pages.
`estimate_pages`, `pages_by_section` and `paginate_sections` expose the same
machinery for previews and tests.

## Report assembly

`ReportBuilder` converts a `ReportSource` (title, findings, evidence, appendix,
metadata) into the canonical section order:

1. **Cover** — title, subtitle and metadata pairs;
2. **Table of contents** — one entry per later section;
3. **Findings** — `ref:severity` entries with detail;
4. **Evidence** — labeled artifacts with source or summary;
5. **Appendix** — numbered notes.

Findings, evidence and appendix start on fresh pages; the TOC flows after the
cover. `ReportFinding` validates the severity vocabulary
(`critical`, `high`, `medium`, `low`, `informational`).

## Export

- `HtmlExporter` emits a standalone document: escaped text, theme CSS
  variables, one `<section class="report-page">` per page, header/footer, and
  `Page n of m` markers.
- `MarkdownExporter` emits a title, metadata, per-page headings, raw lines and
  horizontal rules.
- `ReportRenderer.render(layout, format)` returns a `RenderedReport` with the
  text, pages, page count and a SHA-256 checksum prefix; rendering twice is
  byte-identical.

## Storage (`storage.py`)

`LayoutStore` owns layout identity and secondary indexes for theme, page size,
orientation and section kind. It supports `create`, `put`, `get`, `require`,
`update`, `delete`, `clone`, theme index, stats, snapshot/restore and export
manifests. `ExportManifestEntry` records layout id, format, checksum and page
count; `ExportManifest.digest` is a stable weak ETag over sorted entries.

## API (`api.py`)

Routes registered on a v4 `RouteRegistry`:

```
/api/v4/reports
/api/v4/reports/layouts
/api/v4/reports/themes
/api/v4/reports/pages
/api/v4/reports/render
/api/v4/reports/export
/api/v4/reports/manifest
```

Actions: `describe`, `themes`, `theme`, `layouts`, `layout`, `create`,
`update`, `delete`, `pages`, `build`, `render`, `export`, `manifest`, `stats`.

Handlers always return v4 envelopes via `ok` / `fail`. They require the
`REPORT_DESIGNER` feature gate plus `READ`; mutations require `WRITE`; render,
export and manifest require `EXPORT`. Pagination uses the kernel `paginate`
helper and exposes cursors and ETags in `meta`. Rendering emits a
`REPORT_RENDERED` domain event with an injected clock and id factory, so event
timestamps and ids are reproducible in tests.

The package exposes a kernel-compatible `register(api)` hook discovered by
`redscribe.v4.register_all`.

## Frontend

`frontend/src/features/report-designer/v4/` contains:

- `client.ts` — typed `ReportDesignerClient` over `V4Client`;
- `state.ts` — immutable reducer and pure geometry/summary helpers;
- `PageDesigner.tsx` — section list, theme selector, page size and orientation
  controls, zoom modes, page navigation and a paginated paper preview;
- `report-designer.css` — token-driven styles (`var(--v4-*)`).

The component is a real React slice with keyboard-focusable controls,
`aria-pressed` state for break toggles, labeled form fields and a reduced-motion
and print stylesheet.

## Testing and gates

- Python: theme inheritance and cycles, pagination counts and explicit breaks,
  canonical assembly order, HTML/Markdown content, layout CRUD and envelopes,
  capability/gate errors, event payloads and manifest digests.
- Frontend: reducer transitions, geometry helpers, preview labels and client
  envelope/error handling with `node:test`.

Quality gates: `ruff check`, `ruff format --check`, `mypy`, `pytest`,
`npm test`, `npm run format:check`, `npm run typecheck`, `npm run build`, and
`scripts/loc_gate.py` against the v4 foundation baseline.
