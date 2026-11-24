# V3 Activity Stream (B08)

The V3 activity feature gives the user a reliable memory of what happened and
when. It consumes the B00 typed event bus, projects every meaningful mutation
into a linkable stream entry, and exposes a stable `activity` API namespace.

## Scope and reuse

This branch is additive. It does **not** redefine entities, events, API
envelopes, pagination, capabilities, or configuration. It reuses:

- `redscribe.v3.events` — `DomainEvent`, `EventRecord`, `EventBus`,
  `EventFilter`, `EventReplay`, `RedactionPolicy`.
- `redscribe.v3.entities.types.EntityId` — every activity subject is a
  canonical `kind:value` reference.
- `redscribe.v3.api` — `success()` envelopes, `V3Error`, `PageRequest`,
  `paginate()`, `filter_hash()`, `normalize_request_id()`.
- `redscribe.v3.clock.Clock` / `FixedClock` — all time reads are injected.

No runtime dependencies, network calls, or code execution are introduced.

## Backend layout

| Module | Responsibility |
| --- | --- |
| `models.py` | Immutable projections: `ActivityEntry`, `DateGroup`, `FacetCounts`, `StreamResult`, `Digest`, `DigestCollection`, `VisitMarker`, `SinceLastVisit`, `RetrospectiveSummary`, `RedactionReport`. |
| `projections.py` | Event → entry projection, human titles/summaries, tags, resolver jump targets, date grouping, facets. |
| `filters.py` | Filter DSL parsed into fixed keys; compiles to an entry predicate and lowers to the B00 `EventFilter`. |
| `timezone.py` | IANA timezone resolution and day/week boundary math (including DST). |
| `digest.py` | Deterministic daily/weekly digest buckets, sections, highlights, counts. |
| `visits.py` | Last-visit markers and since-last-visit computation. |
| `retrospective.py` | Window rollups: active days/weeks, streaks, rankings, severity mix, highlights. |
| `redaction.py` | Named rules, allowlist, recursive scrubbing, and redaction reports. |
| `service.py` | `ActivityService` facade combining all of the above with replay-safe ingestion. |

`redscribe.v3.namespaces.activity.register(router)` installs the routes with
`router.add("activity", action, handler)`. The module is discovered by
`install_namespaces()` — no central dispatch table is edited.

### Projection

An `EventRecord` becomes an `ActivityEntry`. The title is derived from the
event kind (`finding.created` → `Finding Created`), the summary from a
preferred payload key (`title`, `name`, `label`, `message`, …). A subject
reference produces a `JumpTarget` with a `/resolve/<kind>/<value>` route, which
is the universal resolver target used by the frontend. Payloads are redacted
before they enter the entry; the names of redacted keys are retained on the
entry so the UI can display a redaction badge.

### Filter DSL

Queries are tokenized into fixed chips; user input is never evaluated as code.

```
kind:finding.created -kind:note.created actor:alice severity:warning tag:web
since:2023-11-14T00:00:00Z until:2023-11-18T00:00:00Z "free text"
```

Supported keys: `kind`, `actor`, `subject`, `severity`, `text`, `since`,
`until`, `correlation`, `tag`. A leading `-` or `!` excludes a value.
`ActivityFilter.to_event_filter()` lowers the record-relevant parts to the B00
`EventFilter`, so B00 filtering semantics remain the single source of truth.
`validate()` returns stable errors instead of throwing for bad tokens.

### Timezone-safe digests

Boundaries are computed with `zoneinfo` in an explicit IANA timezone. A daily
bucket starts at local midnight and ends at the next local midnight, so a
US daylight-saving transition yields a 25-hour (fall) or 23-hour (spring)
bucket rather than overlapping neighbours. Weekly buckets start on Monday.
`generated_at` is supplied by the caller; with a `FixedClock`, digests are
byte-for-byte deterministic.

### Since last visit

A `VisitTracker` stores `(timestamp, sequence)` markers per identity. An entry
is new when its sequence or timestamp is greater than the marker's. With no
marker, all entries are treated as new (first visit). `mark` records the
current stream position; `since` returns new entries, counts, and per-kind /
per-severity breakdowns.

### Retrospectives

`build_retrospective(entries, start, end, timezone)` summarizes a half-open
`[start, end)` window: active days and weeks, longest and trailing consecutive
day streaks, busiest day, top kinds/actors/subjects, severity mix, and the
highest-severity highlights. All rankings break ties by key for determinism.

### Redaction

`ActivityRedactor` wraps the B00 `RedactionPolicy` and text scrubbers. It adds:

- named `RedactionRule` objects that redact values under matching keys;
- an allowlist of display-safe metadata keys (`title`, `status`, `count`, …);
- a `RedactionReport` recording redacted keys, rewritten text values, and
  truncation depth.

The API `redact` route returns both the cleaned payload and its report.

## API routes

All routes are under `/api/v3/activity/` and return V3 envelopes.

| Action | Purpose |
| --- | --- |
| `stream` | Filtered, paginated, date-grouped entries with facets and warnings. |
| `filters` | Filter DSL metadata for chip generation. |
| `validate` | Validate a query string. |
| `digest` | Daily/weekly digests, or one digest when `anchor` is supplied. |
| `since` | New activity for an identity. |
| `mark` | Record a last-visit marker. |
| `retrospective` | Window retrospective summary. |
| `redact` | Redact a payload for display. |
| `entry` | Look up one entry by sequence (including its resolver jump). |
| `stats` | Dashboard counters and redaction totals. |
| `health` | Namespace health and timezone. |
| `modes` | Supported density modes and digest periods. |

Example request body for `stream`:

```json
{
  "query": "kind:finding.created actor:alice",
  "kinds": ["finding.updated"],
  "density": "detailed",
  "offset": 0,
  "size": 25
}
```

Errors use stable B00 codes (`invalid_choice`, `missing_field`,
`invalid_request`, `not_found`, …). Request IDs are propagated from the
`X-Request-ID` header.

## Frontend

`frontend/src/features/activity/` contains:

- `types.ts` — wire types mirroring the Python models;
- `client.ts` — `ActivityClient` over the B00 `V3Client`;
- `filters.ts` — tokenizer, chips, validation, facet suggestions;
- `format.ts` — relative time, day labels, density/period labels, tiles;
- `groups.ts` — client-side sorting, grouping, chip filtering, pagination;
- `state.ts` — reducer and request builders;
- `components/` — `ActivityStream`, `ActivityEntryRow`, `DateGroupView`,
  `DigestCard`, `RetrospectiveView`, `FilterChips`;
- `ActivityFeature.tsx` — panel with stream/digest/retrospective tabs;
- `activity.css` — feature-scoped styles built on `tokens-v3.css`.

Density modes are `compact`, `comfortable`, and `detailed`. Compact rows show
time, severity, title and actor; detailed rows also include payload JSON.
Filter chips come from stream facets and can be toggled or removed. Date groups
are newest-first. Digest cards render highlights with jump buttons. Every
jumpable row and highlight calls the resolver target route supplied by the
host application, so `jump-to-entity` opens the same target as search, graph,
and the command bar.

## Exit criteria

- Every recorded event projects into one visible, linkable activity entry.
- Replaying the same sequences is idempotent (`ActivityService.ingest_all`
  returns zero new rows on a second pass).
- Filter DSL, digest boundaries, and redaction are covered by Python tests.
- Digests and retrospectives are deterministic for a fixed clock and timezone.
- No payload secret reaches the stream, digest, or API response in clear text.
