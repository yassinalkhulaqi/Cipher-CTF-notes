# V2 Evidence Vault

The evidence vault is an additive module under `redscribe.v2.evidence`. It does
not change the v1 note schema and does not require migrations outside the v2
additive SQLite tables created by `SQLiteEvidenceRepository`.

## Scope

- Evidence records with SHA-256 and MD5 digests, MIME detection, and thumbnails.
- Chain of custody with hash-linked events and explicit verification.
- Acquisition provenance, finding links, retention policies, and legal holds.
- Checksummed JSON manifests with preview, import, and bundle export.
- A v2 API namespace with 35 routes under `evidence.*`.
- A standalone React feature under `frontend/src/features/evidence/`.

## Domain modules

| Module | Responsibility |
| --- | --- |
| `models.py` | Records, enums, digests, provenance, custody, links, retention, and manifests. |
| `validation.py` | Field normalization, identifiers, limits, timestamps, and metadata sanitization. |
| `hashing.py` | Digest computation, canonical JSON, chain hashes, and base64 payloads. |
| `mime.py` | MIME detection from magic bytes, text sniffing, filenames, and declared types. |
| `thumbnails.py` | Preview-kind selection and header parsing for images and PDFs. |
| `records.py` | Record construction, filtering, sorting, pagination, and status transitions. |
| `custody.py` | Append-only custody chains and tamper detection. |
| `provenance.py` | Acquisition completeness, checklists, timelines, and merges. |
| `links.py` | Typed evidence-to-finding links and duplicate detection. |
| `retention.py` | Retention decisions, legal holds, and disposition planning. |
| `files.py` | In-memory and directory-backed blob stores. |
| `repositories.py` | In-memory and additive SQLite persistence. |
| `integrity.py` | Digest, blob, custody, and manifest verification reports. |
| `manifests.py` | Manifest construction, parsing, validation, comparison, and import plans. |
| `services.py` | Orchestration API used by both the API layer and tests. |

## Storage model

`SQLiteEvidenceRepository` creates prefixed tables on first use:

- `v2_evidence_records`
- `v2_evidence_custody`
- `v2_evidence_links`
- `v2_evidence_retention`
- `v2_evidence_manifests`

Blob payloads are referenced by an `evidence://` URI. The default service uses
an in-memory store for SQLite-backed vaults; `create_service(storage_root=...)`
selects a directory-backed store for durable payloads.

## API namespace

Routes are registered additively by
`src/redscribe/ui/web/v2/namespaces/evidence.py`. The namespace installer wraps
`ApiV2.__init__` so every v2 API instance receives the routes without changing
the shared kernel route registry.

Route groups:

- Records: `evidence.list`, `view`, `get`, `detail`, `create`, `update`,
  `set_status`, `delete`, `stats`, `search`.
- Ingestion: `ingest`, `ingest_path`, `hash`, `thumbnail`.
- Integrity: `verify`, `verify_all`.
- Custody: `custody.list`, `custody.add`, `custody.verify`.
- Provenance: `provenance.get`, `provenance.update`.
- Links: `links.list`, `links.add`, `links.remove`, `links.view`.
- Retention: `retention.get`, `retention.set`, `retention.hold`, `retention.plan`,
  `retention.apply`.
- Manifests: `manifest.export`, `manifest.json`, `manifest.preview`,
  `manifest.import`, `manifest.bundle`.

All routes use the v2 envelope and participate in request ids, idempotency,
auditing, schema introspection, and capability discovery.

## Frontend feature

`frontend/src/features/evidence/` exports `EvidenceVault`,
`mountEvidenceVault`, `EvidenceVaultApi`, formatting helpers, a reducer, and
typed models. The feature is intentionally standalone so it can be mounted by a
host route without editing shared app shell files.

```tsx
import { mountEvidenceVault } from "./features/evidence";

const unmount = mountEvidenceVault(document.getElementById("root")!);
```

The UI supports drag-and-drop ingestion, filtered tables, integrity badges,
detail inspection, provenance checklists, custody timelines, retention state,
and manifest export/import previews.

## Testing

Backend tests live in `tests/v2_evidence/` and cover hashing, MIME detection,
thumbnails, validation, records, custody, repositories, services, integrity,
links, retention, manifests, route registration, router dispatch, and HTTP
transport.

Frontend tests live in `frontend/scripts/evidence.test.ts` and cover formatting,
filtering, reducer transitions, base64 conversion, and API route targeting.

Run the focused suites with:

```bash
PYTHONPATH=src python3 -m pytest tests/v2_evidence -q -p no:asyncio
cd frontend && npm test
```
