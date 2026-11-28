# RedScribe v4 API

**Base path:** `/api/v4`
**Version:** `v4` (envelope field `meta.version`)
**Transport:** JSON over loopback HTTP only

## 1. Envelope

Every successful response:

```json
{
  "data": { "...": "..." },
  "meta": {
    "request_id": "uuid",
    "version": "v4",
    "page": 1,
    "page_size": 50,
    "etag": "W/\"...\"",
    "next_cursor": "v1..."
  }
}
```

Every failure:

```json
{
  "error": {
    "code": "not_found",
    "message": "resource not found",
    "details": ["id: 123"]
  }
}
```

## 2. Error codes

| Code | HTTP | Meaning |
| --- | ---: | --- |
| `not_found` | 404 | Entity or route does not exist |
| `invalid_input` | 400 | Validation failed |
| `conflict` | 409 | Version, ETag, or duplicate conflict |
| `forbidden` | 403 | Missing capability or disabled feature |
| `unavailable` | 503 | Local service or vault unavailable |
| `internal` | 500 | Unexpected failure |

## 3. Conventions

- **Request IDs.** Clients send `X-Request-ID`; the server echoes it in `meta.request_id`.
- **Pagination.** `?page=&page_size=`; `meta.next_cursor` is opaque and versioned.
- **ETags.** `If-None-Match` is compared with `meta.etag`; matches return 304.
- **Capabilities.** Routes call `FeatureGate.require(flag)` before mutating.
- **No shell.** No endpoint accepts a command string. Playbook nodes are declarative.

## 4. Routes

Routes are registered additively by each feature branch through
`redscribe.v4.api_v4.register_routes`. The canonical set after all branches merge:

| Prefix | Methods | Feature |
| --- | --- | --- |
| `inbox` | GET, POST, PATCH | Capture inbox |
| `findings` | GET, POST, PUT | CVSS v4 findings |
| `evidence` | GET, POST | Evidence lab |
| `blocks` | GET, PUT, PATCH | Pro editor |
| `query` | GET, POST | Query language |
| `automation` | GET, POST | DAG runs |
| `reports` | GET, POST | Report designer |
| `graph` | GET | Graph workbench |
| `vault` | GET, POST | Security vault |
| `accessibility` | GET, PATCH | A11y/i18n preferences |

## 5. Frontend client

`frontend/src/features/v4-kernel/client.ts` exposes `V4Client`:

```ts
const client = new V4Client();
const { data, meta } = await client.get<InboxItem[]>("/inbox", { page: 1 });
await client.post("/findings", { title: "SQLi", cvss_vector: "CVSS:4.0/..." });
```

`V4ApiError` carries `code`, `message`, and `details`, mirroring the error envelope.

## 6. Compatibility

- v1, v2, and v3 adapters remain untouched and green.
- The envelope decoder rejects a wrong `meta.version` with `conflict`.
- Schema migrations are append-only v5→v6; downgrades are refused.
