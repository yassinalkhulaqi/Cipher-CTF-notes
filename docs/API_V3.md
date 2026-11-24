# API v3

Base path: `/api/v3`. Content type: `application/json`. All mutations are
`POST` unless a route declares additional methods.

## Envelopes

Success:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_...",
    "api_version": "3.0",
    "etag": "\"...\"",
    "page": { "page": 1, "page_size": 50, "total": 0, "has_next": false, "has_previous": false },
    "warnings": []
  }
}
```

Error:

```json
{
  "error": {
    "code": "not_found",
    "message": "Unknown finding",
    "field": "ref",
    "retryable": false,
    "context": {}
  },
  "meta": { "request_id": "req_...", "api_version": "3.0" }
}
```

## Error codes

`unknown_route`, `not_found`, `invalid_request`, `invalid_json`, `invalid_type`,
`missing_field`, `invalid_choice`, `field_too_long`, `invalid_cursor`,
`unsupported_media_type`, `payload_too_large`, `idempotency_conflict`,
`conflict`, `precondition_failed`, `rate_limited`, `forbidden`, `internal`.

Default statuses: 400 for validation, 404 for unknown route/not found, 409 for
conflicts, 412 for stale ETag, 413 for oversized bodies, 415 for wrong media
type, 429 for throttling, 403 for denied capability, 500 for internal errors.

## Headers

- `X-Request-ID` — caller request id; generated server-side when absent.
- `If-None-Match` — strong ETag from a previous `meta.etag`.
- `Idempotency-Key` — 1–200 characters; repeated keys must repeat the payload.
- `X-Capability` — optional capability check performed by feature routes.

## Pagination

`offset`/`size` or an opaque `cursor`. Page size defaults to 50, max 200.
Cursors carry a checksum; tampered cursors return `invalid_cursor`. List
responses include `meta.page` and, when there is a next page, a cursor in
`data.next_cursor`.

## Namespaces

| Namespace | Owner branch | Purpose |
| --- | --- | --- |
| `system` | B00 | health, manifest, capabilities, info |
| `commands` | B01 | command registry, macros, navigation |
| `findings` | B02 | finding lifecycle, CVSS, remediation |
| `evidence` | B03 | evidence lab, hex, custody |
| `graph` | B04 | layouts, clusters, paths, snapshots |
| `search` | B05 | query v2, facets, pivots, saved searches |
| `automation` | B06 | DAG runs, dry-run, variables |
| `reports` | B07 | layouts, themes, render, redaction |
| `activity` | B08 | stream, filters, digests |
| `sync` | B09 | bundles, merge, conflicts |
| `security` | B10 | encryption lifecycle, policies, audit |
| `performance` | B11 | benchmarks, budgets, index state |
| `a11y` | B12 | audits, locales, themes, shortcuts |
| `extensions` | B13 | manifests, capabilities, SDK |
| `release` | B14 | golden paths, diagnostics |

Namespaces are discovered at runtime from `redscribe.v3.namespaces`. A route is
registered by calling `router.add(namespace, action, handler)` inside a module's
`register(router)` function.
