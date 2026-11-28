# Findings v4 — CVSS v4 finding studio

This feature makes findings first-class citizens of the v4 platform. A finding
carries a validated CVSS v4 vector, a computed score with severity band, a
governed lifecycle state, remediation metadata and a retest audit trail. The
backend and the React studio share the same vocabulary so a score shown in the
editor matches the score persisted by the API.

## Layout

| Path | Purpose |
| --- | --- |
| `src/redscribe/v4/findings_v4/types.py` | Metric enums, vectors, severity, lifecycle, finding records |
| `src/redscribe/v4/findings_v4/service.py` | Scoring calculator and finding operations |
| `src/redscribe/v4/findings_v4/storage.py` | Indexed in-memory store and snapshot export |
| `src/redscribe/v4/findings_v4/api.py` | Capability-checked v4 envelope handlers |
| `frontend/src/features/finding-cvss-v4/` | Typed client, reducer and `FindingStudio` UI |
| `frontend/scripts/v4-finding-cvss-v4.test.ts` | Node test suite for client and reducer |
| `tests/v4_findings_v4/` | Python tests for types, services, storage and API |

## Metric vocabulary

`CvssV4Vector` accepts the fifteen canonical CVSS v4 metric codes:

- Base — `AV`, `AC`, `AT`, `PR`, `UI`, `VC`, `VI`, `VA`, `SC`, `SI`, `SA`
- Threat — `E`
- Environmental — `CR`, `IR`, `AR`

`CvssV4Vector.parse` validates the `CVSS:4.0` prefix, rejects duplicate, unknown
and incomplete metrics, and accepts metrics in any order. `format` always emits
the canonical order with all optional metrics defaulted to `X`. `to_dict` and
`from_dict` round-trip through JSON-safe mappings.

## Scoring pipeline

The calculator uses documented CVSS v4-style lookup tables:

| Metric | Weights |
| --- | --- |
| `AV` | N 0.85, A 0.62, L 0.55, P 0.20 |
| `AC` | L 0.77, H 0.44 |
| `AT` | N 1.00, P 0.90 |
| `PR` | N 0.85, L 0.62, H 0.27 |
| `UI` | N 0.85, P 0.62 |
| Impact (`VC`/`VI`/`VA`/`SC`/`SI`/`SA`) | H 0.56, L 0.22, N 0.00 |
| `E` | X/A 1.00, P 0.97, U 0.60 |
| Requirements (`CR`/`IR`/`AR`) | X/M 1.00, H 1.50, L 0.50 |

Impact sub-score: vulnerable-system and subsequent-system components are
combined as `1 - (1-c)(1-i)(1-a)`. When no subsequent impact is present, the
score is `6.42 * isc_vuln`; otherwise the combined form
`7.52 * (isc_vuln + isc_sub - isc_vuln*isc_sub)` is used. Requirement weights
are capped at `0.915`.

Exploitability sub-score: `8.22 * AV * AC * AT * PR * UI`, multiplied by the
`E` weight for threat and environmental scores.

Scores are `min(impact + exploitability, 10)`, rounded up to one decimal and
clamped to `0.0–10.0`. Three flavours are produced:

- **Base** — ignores threat maturity and requirements.
- **Threat** — applies exploit maturity.
- **Environmental** — applies both exploit maturity and requirements; this is
  the effective score used for the finding's severity.

Severity bands follow CVSS v4: `none` 0.0, `low` 0.1–3.9, `medium` 4.0–6.9,
`high` 7.0–8.9, `critical` 9.0–10.0. Nomenclature is `CVSS:B`, `CVSS:BT`,
`CVSS:BE` or `CVSS:BTE` depending on which optional metric groups are defined.

## Lifecycle

Legal transitions are declared in one table and enforced by both the service
and the reducer:

- `draft` → `open`
- `open` → `confirmed`, `closed`, `accepted_risk`
- `confirmed` → `remediating`, `accepted_risk`
- `remediating` → `retest`, `open`
- `retest` → `closed`, `remediating`
- `closed` → `open`
- `accepted_risk` → `open`

Any other edge raises an `illegal_transition` domain error, mapped to a `409`
conflict envelope by the API.

## Domain operations

`FindingService` creates findings, re-scores them, transitions state, assigns
remediation due dates and notes, and records retests. A retest increments the
finding's `retest_count`, appends an immutable `RetestRecord` to the store, and
moves the state to `closed` on `pass` or back to `remediating` on `fail` and
`partial`. Domain events `FINDING_CREATED`, `FINDING_SCORED` and
`FINDING_RETESTED` are published through the shared v4 event bus.

## API

Routes register at `/api/v4/findings` through the platform route registry.

- `GET /findings` — paginated list with `severity` and `state` filters, weak
  ETag/`If-None-Match` support and v4 envelopes.
- `GET /findings?view=snapshot` — JSON-safe snapshot export (`EXPORT` capability).
- `POST /findings` — create and score a finding (`WRITE` capability).
- `PUT /findings` — `action` is one of `score`, `transition`, `remediation` or
  `retest`, each with the required fields.

Every request is checked against the `CVSS_V4` feature gate and the relevant
capability. Errors use the shared `ApiError` codes (`invalid_input`,
`not_found`, `conflict`, `forbidden`) inside `fail()` envelopes.

## Studio UI

`FindingStudio` is a self-contained React slice using `useReducer`. It provides:

- a vector editor with a select per metric, grouped by base, threat and
  environmental metrics;
- a live SVG score gauge coloured by severity using `--v4-*` tokens;
- lifecycle chips and buttons for the legal transitions of the selection;
- remediation due date and notes, plus retest verdict and note controls;
- a findings list and an activity log.

`FindingClient` wraps the kernel `V4Client`, so decoding, request ids and
structured errors behave identically to other v4 features.

## Verification

```sh
python3 scripts/loc_gate.py --baseline 9f0459cf510def70e9e78f08b54ec86795c246be \
  --min-added 2500 --min-net 2500 --min-test-loc 400
python3 -m ruff check . && python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
cd frontend && npm test && npm run format:check && npm run typecheck && npm run build
```
