# Reporting Studio V2

The reporting studio turns vault notes into deterministic, citable reports. It is
implemented as an additive V2 capability: the backend lives in
`redscribe.v2.reporting`, and the API namespace lives in
`redscribe.ui.web.v2.namespaces.reporting`. No shared route tables are edited.

## Capabilities

- Build a report document from a declarative configuration.
- Preview finding severity, evidence coverage, warnings, and section outline.
- Render to Markdown, HTML, compact JSON, or print-oriented HTML.
- Export single formats or multi-format bundles with reproducibility manifests.
- Validate report configurations before rendering.
- Explain inclusion decisions and redact sensitive values.
- Reorder or move sections in a supplied outline.

## Backend layout

| Module | Responsibility |
| --- | --- |
| `models.py` | Core immutable data models and JSON serialization. |
| `severity.py` | Severity parsing, counting, sorting, and risk labels. |
| `validation.py` | Configuration and format validation. |
| `source.py` | Deterministic vault-to-source snapshot conversion. |
| `evidence.py` | Evidence extraction, excerpting, and coverage stats. |
| `inclusion.py` | Rule matching, selection, and confidence helpers. |
| `sections.py` | Outline traversal, ordering, renumbering, and cloning. |
| `templates.py` | Built-in report template definitions. |
| `redaction.py` | Redaction rules, application, and preview spans. |
| `markdown_render.py` | Markdown output. |
| `html_render.py` | HTML output and escaping. |
| `json_render.py` | Stable JSON output. |
| `print_layout.py` | Print profiles and generated print CSS. |
| `manifest.py` | Reproducibility digests and manifests. |
| `serialization.py` | Parsing external payloads into typed models. |
| `pipeline.py` | High-level `ReportingService` used by API handlers. |

## API namespace

Call routes through the V2 client with names prefixed by `reporting.`:

```python
from redscribe.ui.web.v2.namespaces.reporting import register

register(api)
```

Browser callers use `ReportingClient`:

```ts
import { V2Client } from "../lib/apiClient";
import { ReportingClient } from "../features/reporting/client";

const reporting = new ReportingClient(new V2Client());
const preview = await reporting.preview({ title: "Engagement Report" });
```

### Route reference

| Route | Purpose | Required fields |
| --- | --- | --- |
| `reporting.health` | Availability, formats, templates, profiles | — |
| `reporting.templates` | List template summaries | — |
| `reporting.template` | Return one full template | `key` |
| `reporting.profiles` | List print profiles | — |
| `reporting.config_schema` | Editor-facing field schema | — |
| `reporting.sections` | Template outline or parsed outline | — |
| `reporting.source` | Deterministic source snapshot | — |
| `reporting.build` | Build a report document | — |
| `reporting.preview` | Lightweight builder preview | — |
| `reporting.validate` | Validate a configuration | — |
| `reporting.severity` | Severity analytics | — |
| `reporting.inclusion` | Inclusion decision report | — |
| `reporting.render` | Render one output | `format` |
| `reporting.export` | Render and optionally write to disk | `format` |
| `reporting.bundle` | Render several formats plus manifest | `directory` |
| `reporting.manifest` | Reproducibility manifest | — |
| `reporting.redact` | Redact and preview sample text | `text` |
| `reporting.redaction_rules` | Built-in redaction rules | — |
| `reporting.reorder` | Reorder outline children | `sections`, `parent_id`, `order` |
| `reporting.move` | Move one outline section | `sections`, `identifier`, `parent_id`, `index` |

## Configuration

A report configuration is a plain JSON object. The important fields are:

```json
{
  "title": "Engagement Report",
  "template": "engagement",
  "client": "Example Org",
  "author": "Operator",
  "classification": "confidential",
  "scope": ["Web application", "All discovered hosts"],
  "tags": ["web", "active"],
  "statuses": ["confirmed"],
  "minimum_severity": "low",
  "page_size": "a4",
  "orientation": "portrait",
  "print_profile": "standard",
  "include_evidence": true,
  "include_appendices": true,
  "redact_sensitive": true,
  "notes": "Final delivery notes."
}
```

- `generated_at` pins source snapshots and digests. Omit it for the live clock.
- `sections` accepts a full outline; omit it to clone the selected template.
- `rules` controls which source notes become findings.
- `redactions` replaces or extends the built-in redaction rules.
- `findings` provides explicit findings when no vault source is needed.

## Templates

Built-in template keys:

- `engagement`: standard client-facing report with evidence and appendices.
- `pentest`: technical assessment layout with detailed evidence.
- `ctf`: competition write-up with challenge and artifact sections.
- `incident`: incident timeline and remediation structure.
- `executive`: compact management summary.

## Render formats

| Format | Extension | MIME type |
| --- | --- | --- |
| `markdown` | `.md` | `text/markdown` |
| `html` | `.html` | `text/html` |
| `json` | `.json` | `application/json` |
| `print` | `.html` | `text/html` |

`print` uses the selected print profile, page size, orientation, cover, and TOC
settings. Available profiles are `standard`, `technical`, `compact`,
`landscape`, and `letter`.

## Determinism

Reports are reproducible when `generated_at` is fixed:

- Source notes are sorted by path, title, and identifier.
- Findings are sorted by severity rank, confidence, and identifier.
- JSON uses sorted keys and compact separators.
- Manifests include source, template, rule, redaction, and print digests.
- Rendered digests are added to the manifest when content is available.

Use `reporting.bundle` with an explicit `directory` to write all outputs and a
`manifest.json` side by side.

## Redaction

Built-in rules cover flags, private keys, credentials, tokens, API keys, email
addresses, and IP addresses. Host redaction can be enabled with
`reporting.redaction_rules` and `include_hosts: true`.

`reporting.redact` returns:

- `text`: redacted output.
- `applied`: rule names that matched.
- `counts`: match counts per rule.
- `preview`: spans with matched text and surrounding context.
- `rules`: normalized rules used for the operation.

## Frontend feature

`frontend/src/features/reporting/` contains a self-contained studio UI:

- `client.ts`: typed wrapper over `V2Client`.
- `state.ts`: reducer, defaults, payload mapping, and signature helpers.
- `format.ts`: display formatting for severity, evidence, manifests, and output.
- `ReportingStudio.tsx`: form, preview, validation, redaction, and download UI.
- `reporting.css`: studio layout and status styling.

The feature is designed to be mounted by a host route without changing the
shared route registry.

## Tests

- Python tests cover models, rendering, internals, and the API namespace under
  `tests/v2_reporting/`.
- The frontend test `frontend/scripts/reporting.test.ts` covers state, helpers,
  and client route payloads.

Run the checks with:

```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
cd frontend && npm test && npm run format:check && npm run typecheck && npm run build
```
