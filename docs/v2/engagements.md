# V2 Engagement Core

Engagement Core is the first feature slice built on the v2 platform kernel. It
adds engagement planning, scope management, target inventory, findings,
duplicate detection, workflow state machines, and dashboard rollups without
changing v1 behavior or shared v2 platform files.

## Scope

The branch adds three layers:

- A domain layer in `src/redscribe/v2/engagements/` with immutable-style models,
  validators, repositories, services, state machines, analytics, and errors.
- An additive API namespace in
  `src/redscribe/ui/web/v2/namespaces/engagements.py` that registers 53 routes
  through the host registry's `_register` hook.
- A frontend feature in `frontend/src/features/engagements/` composed from the
  v2 UI kit and typed `V2Client` wrapper.

Shared route tables, the shipped app shell, and root route registry are left
unchanged. The frontend feature is ready for a later shell-wiring change.

## Domain model

An engagement owns all operational records through integer `engagement_id`
references:

| Entity | Purpose |
| --- | --- |
| `Engagement` | Client, owner, dates, kind, status, tags, and derived key |
| `ScopeRule` | Include or exclude rules by domain, IP, CIDR, URL, keyword, port, or tag |
| `Target` | In-scope host, domain, network, URL, application, or cloud asset |
| `Asset` | Concrete server, workstation, database, device, identity, or cloud resource |
| `Service` | Network service with port, protocol, product, version, and verification status |
| `Credential` | Username and secret reference with kind and validation lifecycle |
| `Finding` | Security issue with severity, confidence, CVSS, evidence, owner, status, and duplicate links |
| `Activity` | Append-only audit summaries for entity changes |
| `FindingEvent` | Per-finding workflow history |

Models expose stable `as_dict()` snapshots and parse them with `from_dict()`.
Credential detail responses use `safe_dict()` so secrets stay behind references.

Repositories assign sequential integer IDs, filter by engagement, support
snapshots, and are aggregated by `EngagementStore`. `snapshot()` and
`restore()` exchange versioned plain dictionaries; the store ignores malformed
non-mapping entries during restore.

## Validation

`validation.py` centralizes payload cleaning and returns a `ValidationReport`
with field-level issues. It validates:

- identifiers, names, descriptions, hosts, IPs, CIDRs, URLs, tags, and dates;
- engagement date order and required metadata;
- scope rule expression kind/value/action compatibility;
- target values and kind detection;
- asset, service, and credential fields;
- finding fields, enum choices, CVSS vectors, CWE/CVE lists, references, and
  relationships between target, asset, service, and canonical findings.

Service methods convert failed validation reports into `EngagementError` with
code `engagement_validation_failed` and `details.issues`. The API namespace
translates those errors into v2 `V2Error` envelopes with `status`, `code`,
`message`, `details`, and `retryable` fields.

## Workflows

State transitions are declarative `StateMachine` instances defined in
`state_machine.py`. Guards can require a note, reason, evidence, duplicate ID,
or boolean flag, so UI actions and API routes share the same rules.

| Entity | Transitions |
| --- | --- |
| Engagement | `plan -> active -> reporting -> closed -> archived` with report sign-off guard on closure |
| Target status | `confirm`, `test`, `retest`, `exclude`, `restore`, `out_of_service` |
| Target scope | `propose`, `accept`, `reject`, `waive`, `revoke`, `exclude`, `include`, `reset` |
| Service | `discover`, `verify`, `test`, `close`, `reopen` |
| Credential | `validate`, `invalidate`, `revoke`, `rotate`, `retry` |
| Finding | `submit`, `verify`, `accept_risk`, `reopen`, `mark_duplicate`, `unduplicate`, `remediate`, `close` |

`available_actions()` powers controls in the frontend. `describe_workflows()`
is exposed through `engagements.workflows` for schema introspection.

## Findings and analytics

CVSS v3.1 vectors are parsed and scored in `cvss.py`. Severity bands are
`info`, `low`, `medium`, `high`, and `critical`; the frontend maps those bands
to neutral, low, medium, high, and critical presentation tones.

Duplicate detection compares normalized title, summary, target, asset, service,
CVSS vector, CWE/CVE sets, evidence steps, and tags. `find_duplicates_for()`
returns scored candidates with reasons; `finding_clusters()` groups findings by
transitive canonical links. `mark_finding_duplicate()` and
`link_duplicate_cluster()` maintain links and record workflow events.

Coverage reporting scores scope confirmation, inventory depth, credential
coverage, finding coverage, and evidence quality. Engagement rollups produce
status, risk, severity matrix, owner, and stale-finding summaries for the
dashboard. Portfolio rollups aggregate all engagements with pagination.

## API namespace

`EngagementNamespace` binds handlers to one `EngagementService`. Calling
`register(api, service)` discovers `api._register`, wraps every handler with
error translation, and supplies stable route metadata. `configure(service)`
sets the process-wide namespace used by bare `register(api)`.

Route groups:

| Group | Routes |
| --- | --- |
| Engagements | `list`, `get`, `create`, `update`, `transition`, `delete`, `dashboard`, `portfolio`, `workflows`, `options`, `activity`, `seed_demo` |
| Scope | `list`, `add`, `remove`, `evaluate`, `import` |
| Targets | `list`, `get`, `create`, `update`, `transition`, `scope_transition`, `remove`, `coverage` |
| Assets | `list`, `get`, `create`, `update`, `remove` |
| Services | `list`, `get`, `create`, `update`, `transition`, `remove` |
| Credentials | `list`, `get`, `create`, `update`, `rotate`, `transition`, `remove` |
| Findings | `list`, `get`, `create`, `update`, `transition`, `duplicate`, `link_cluster`, `duplicates`, `clusters`, `remove` |

List handlers accept opaque `cursor` and `limit` values and return `Page`
metadata plus deterministic ETags. Detail handlers return ETags and stable
status codes. Mutating routes carry `mutating=True` and an `entity_type` so the
shared v2 idempotency and audit layers continue to work.

Engagement-domain error codes remain stable:

| Code | Meaning |
| --- | --- |
| `engagement_not_found` | Entity does not exist or is outside the engagement |
| `engagement_validation_failed` | Payload failed one or more field checks |
| `engagement_conflict` | Duplicate key, value, or relationship |
| `engagement_transition_denied` | Action is not allowed from the current state or guard failed |
| `engagement_operation_failed` | Generic domain operation failure |

## Frontend feature

The frontend feature is self-contained and exports `EngagementFeature` from
`frontend/src/features/engagements/index.ts`. `EngagementApi` wraps all 53
routes, generates request IDs and idempotency keys for mutations, and normalizes
list responses into `{ items, page }`.

`logic.ts` holds pure helpers for filtering, sorting, action labels, risk bands,
severity ordering, scope decisions, and status presentation. UI components cover:

- engagement list and summary detail;
- scope editor with rule evaluation;
- target table with workflow and scope controls;
- asset, service, and credential inventory tables;
- finding editor with CVSS, evidence, owner, and duplicate controls;
- dashboard widgets for coverage, severity, risk, and stale findings.

Styles live in `frontend/src/features/engagements/styles.css` and are imported
from the root stylesheet. Components reuse v2 UI-kit primitives for buttons,
fields, tabs, tables, banners, dialogs, and toasts.

## Testing and verification

Backend tests live in `tests/v2_engagements/` and cover models, validation,
utilities, state machines, CVSS, duplicates, analytics, repositories, services,
and API namespace handlers. Frontend tests live in
`frontend/scripts/engagements.test.ts` and are registered in
`frontend/scripts/test.mjs`.

Required checks before merge:

```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
cd frontend && npm test && npm run format:check && npm run typecheck && npm run build
python3 scripts/loc_gate.py --base origin/dev/v2-00-platform-kernel --min-added 4000 --min-tests 500
```

## Compatibility rules

- Do not edit shared v2 platform modules from this branch.
- Add routes only through the engagement namespace registry.
- Keep response shapes additive; rename fields only in a future namespace version.
- Keep `findings` and `engagements` identifiers as integers in API payloads.
- Preserve v1 behavior; this branch does not change the shipped app shell.
