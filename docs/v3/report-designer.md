# V3 Report Designer

The report designer turns a design specification into a deterministic,
client-ready deliverable. It lives in `redscribe.v3.report_designer` and is
exposed through the `reports` API namespace. It reuses the V3 entity contracts
for identity and the V3 envelope/router contracts for transport; it never
redefines them.

## Design goals

- **One tree, every output.** The same `LayoutDocument` drives pagination, the
  table of contents, and all four renderers, so the print preview and the
  exports are structurally identical.
- **Determinism.** Digests, anchors, page numbers, and rendered bytes are pure
  functions of a design. Re-running a design with the fixed clock produces the
  same manifest digest.
- **Offline only.** No network calls, telemetry, or command execution. All
  rendering is local string generation.

## Package layout

| Module | Responsibility |
| --- | --- |
| `identifiers.py` | canonical JSON, digests, slugs, anchors, page labels |
| `model.py` | severity, sections, findings, evidence, rules, layout document |
| `themes.py` | theme tokens, four built-in themes, isolated theme registry |
| `pagination.py` | line estimation, forced breaks, continuation pages, anchor map |
| `builders.py` | cover, resolved TOC, and appendix section builders |
| `selection.py` | stable finding inclusion rules and decision auditing |
| `redaction.py` | built-in patterns, live span previews, whole-tree redaction |
| `renderers/` | HTML, Markdown, canonical JSON, print CSS, renderer registry |
| `engine.py` | `DesignSpec` → `DesignResult` pipeline and manifest |
| `dto.py` | validated conversion of API payloads into domain objects |

## Pipeline

1. **Select.** `SelectionPolicy` applies ordered include/exclude rules to the
   candidate findings. Ordering is derived from severity and stable keys, not
   input order; every candidate gets a recorded decision.
2. **Assemble.** Selected findings are placed in a generated `Findings`
   section. Cover and appendices are generated from document metadata.
3. **Redact.** Enabled rules are applied to every visible text field before
   anything is measured or rendered. `preview_document` returns the exact spans
   (rule, offsets, context, replacement) consumed by the React designer.
4. **Paginate.** `PaginationEngine` estimates line height from theme character
   width, splits oversized sections into continuation fragments, and resolves
   every section anchor to a page number.
5. **Resolve the TOC.** The table of contents is rebuilt until the anchor map is
   stable (a fixed point), so page numbers never drift between passes.
6. **Render.** The renderer registry emits HTML, Markdown, JSON, and print CSS
   in canonical order. `PrintCssRenderer` reads the same theme tokens used by
   the HTML renderer.

## Manifest

Every design result carries a manifest with digests for the canonical spec,
theme, selection, redaction rules, pagination plan, and document. The overall
`design_digest` is independent of which output formats were requested, so a
preview and a full export of the same design share one identity.

## Themes

`client`, `technical`, `executive`, and `print` ship as built-ins. Themes are
frozen token bundles: selecting one cannot mutate another. Print CSS is derived
from the active tokens, including page size, orientation, margins, TOC leaders,
and watermark settings.

## API routes

| Action | Purpose |
| --- | --- |
| `health` | status, capability, formats, theme count |
| `themes` | full theme descriptors and picker summaries |
| `formats` | render formats with mime types and extensions |
| `design` | full design result including rendered outputs |
| `preview` | redaction spans, pagination summary, TOC, selection |
| `paginate` | resolved page plan and TOC entries |
| `render` | one output; body includes `format` |
| `manifest` | reproducibility metadata without rendered bodies |
| `redact` | redaction preview and active rules |
| `validate` | validation issues and rule summary |

Routes are registered by `redscribe.v3.namespaces.reports.register(router)`
using `router.add("reports", action, handler)`. Dynamic discovery installs the
namespace automatically; no central dispatch table is edited.

## Frontend

`frontend/src/features/report-designer/` contains the page designer:

- drag-to-reorder section rows with visibility, TOC, and page-break toggles;
- zoom controls and a scaled pagination preview with resolved page labels;
- a theme picker bound to the reports namespace;
- inline redaction rule editing with live match previews;
- a print-ready preview mode that hides editor chrome and matches the export
  structure byte-for-byte in section order.

The feature owns its CSS (`report-designer.css`) and consumes only V3 foundation
tokens. Its pure helpers and reducer are covered by
`frontend/scripts/report-designer-v3.test.ts`.

## Tests

`tests/v3_report_designer/` covers identifiers/model validation, theme
isolation, pagination across fixtures (including continuation splits and forced
breaks), cover/TOC/appendix builders, inclusion rules, redaction completeness,
all four renderers, engine determinism, DTO validation, and namespace dispatch.
