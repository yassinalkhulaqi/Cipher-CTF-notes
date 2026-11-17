# API v2

API v2 is a versioned envelope layered over the existing localhost JSON RPC
transport. It is available at `POST /api/v2/{namespace}/{action}` with
`Content-Type: application/json`.

## Success envelope

```json
{
  "ok": true,
  "data": { "id": 1, "title": "Example" },
  "meta": {
    "request_id": "req_abc123",
    "api_version": "2.0",
    "etag": "sha256:...",
    "page": { "cursor": null, "next": "...", "total": 12, "limit": 50, "has_more": false }
  }
}
```

`meta.page` and `meta.etag` are omitted when not applicable. Responses are
serialized with stable key order so an idempotent replay is byte-identical.

## Error envelope

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Note does not exist",
    "details": {},
    "retryable": false,
    "request_id": "req_abc123"
  }
}
```

| Code | HTTP | Meaning |
| --- | --- | --- |
| `unknown_route` | 404 | Route name is missing or malformed |
| `not_found` | 404 | Requested entity does not exist |
| `invalid_request` | 400 | Body or field shape is invalid |
| `invalid_json` | 400 | Body is not valid JSON |
| `invalid_type` | 400 | Field has the wrong JSON type |
| `missing_field` | 400 | Required field is absent |
| `invalid_choice` | 400 | Field value is not in the allowed set |
| `field_too_long` | 400 | Field exceeds its documented limit |
| `invalid_cursor` | 400 | Cursor cannot be decoded or validated |
| `unsupported_media_type` | 415 | `Content-Type` is not `application/json` |
| `payload_too_large` | 413 | Body exceeds 8 MiB |
| `idempotency_conflict` | 409 | Key was reused with a different request |
| `conflict` | 409 | Domain-level conflict |
| `internal` | 500 | Unexpected server failure |

## Request IDs

Clients may send `X-Request-ID` (1–128 safe characters). Invalid IDs are
replaced with `req_<token>`. The accepted value appears in both the response
header and envelope. Replays return the original stored envelope body.

## Idempotency

Mutating routes accept `Idempotency-Key` (1–200 safe characters). The key is
hashed together with the route and request body. Reusing the key with the same
body replays the stored response without repeating the mutation. Reusing it
with a different body returns `idempotency_conflict`.

```http
POST /api/v2/notes/create HTTP/1.1
Content-Type: application/json
Idempotency-Key: note-create-2026-11-17-001

{"title":"Report","content":"# Report"}
```

Records expire after 24 hours and are pruned after each keyed mutation.

## Pagination

List routes accept `cursor` and `limit` (1–200, default 50). Cursors are opaque
base64url tokens. `meta.page.next` is passed back as the next `cursor`.

```json
{"cursor":null,"limit":50,"namespace":"notes","query":"web"}
```

## Routes in B00

| Route | Purpose |
| --- | --- |
| `system.health` | Liveness, version, vault counts |
| `system.capabilities` | Enabled feature flags and limits |
| `system.api_schema` | Route/contract inventory |
| `system.events` | Filtered entity event journal |
| `notes.list` | Paginated note summaries with query filtering |
| `notes.get` | Note detail with ETag |
| `notes.create` | Idempotent note creation |
| `notes.update` | Idempotent metadata update |
| `notes.save_content` | Idempotent content write |
| `notes.trash` | Idempotent soft delete |

Future branches reserve their namespace: `engagements`, `targets`, `assets`,
`services`, `credentials`, `findings`, `evidence`, `snippets`, `templates`,
`graph`, `reports`, `sync`, and `security`.

## Frontend client

`frontend/src/lib/apiClient.ts` implements the envelope contract with typed
errors, `AbortController` cancellation, one retry for safe reads, generated
request IDs, and cursor pagination. The shipped `frontend/src/lib/api.ts` is
unchanged; feature branches migrate call sites incrementally.

## Compatibility rules

- Never change a v1 method name or payload in a v2 branch.
- Add fields to v2 responses rather than renaming them.
- A new error code requires a test and a row in this document.
- Breaking v2 changes require a new namespace version, not a silent edit.
