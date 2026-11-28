# Evidence Lab (v4)

The v4 Evidence Lab turns evidence metadata into a deterministic inspection
workbench. It maps bytes that a caller has already supplied into hex rows,
extracts printable strings, verifies digests, verifies an append-only custody
chain, and diffs two evidence snapshots. It never reads files, runs commands,
evaluates expressions, or opens network connections.

## Layout

| Area | Path |
| --- | --- |
| Types | `src/redscribe/v4/evidence_lab/types.py` |
| Services | `src/redscribe/v4/evidence_lab/service.py` |
| Storage | `src/redscribe/v4/evidence_lab/storage.py` |
| API | `src/redscribe/v4/evidence_lab/api.py` |
| Tests | `tests/v4_evidence_lab/` |
| Frontend | `frontend/src/features/evidence-lab/v4/` |
| Frontend tests | `frontend/scripts/v4-evidence-lab.test.ts` |

The v3 evidence-lab feature already lives at `frontend/src/features/evidence-lab/`
and is covered by the active `03.json` suite. The v4 slice is additive: it lives
in the nested `v4/` directory so both generations coexist without overwriting
existing modules.

## Value objects

`types.py` defines strict, frozen dataclasses that validate themselves and
round-trip through `to_dict()` / `from_dict()`:

- `HashAlgorithm` (`sha256`, `sha1`, `md5`) with digest sizes and labels.
- `EvidenceRecord` — id, name, size, SHA-256 digest, acquisition timestamp, tags.
- `HexCell` and `HexRow` — one byte rendered as `offset`, `hex`, and `ascii`.
- `StringEncoding` and `StringHit` — printable runs with an encoding tag.
- `HashVerification` — expected vs. computed digest with a consistency check.
- `CustodyAction` and `CustodyEntry` — actor, action, timestamp, and link hashes.
- `ChainVerification` / `ChainIntegrityResult` — chain validation outcomes.
- `InspectionResult` — aggregated hex rows, strings, verifications, custody.

`require_text`, `require_int`, `normalize_tags`, `is_hex_digest`, and
`printable_ascii` are shared validators. Domain errors derive from
`EvidenceLabError`.

## Services

`HexDumper` emits fixed-width rows (16 bytes by default), an ascii column, and
rendered text lines. Offsets are caller-controlled, so a window can start at an
arbitrary base address.

`StringExtractor` scans printable ASCII and UTF-16LE runs above a minimum
length, optionally de-duplicating by value while keeping the first offset. It
also exposes `filter` and `top` helpers.

`HashVerifier` computes SHA-256, SHA-1, and MD5 digests through `hashlib`,
compares them with `hmac.compare_digest`, and can verify a record, a manifest of
several algorithms, or produce the canonical digest used to link custody
entries.

`CustodyGraph` is append-only. Each entry's `to_hash` is the digest of its
predecessor hash, timestamp, actor, action, sequence index, and evidence id.
`verify_chain` recomputes every link and reports the first broken index;
`tampered_copy` supports negative tests.

`BundleDiffer` compares two snapshots and reports added, removed, changed, and
unchanged ids plus field-level `DiffItem` records. `InspectionPipeline` composes
the inspectors and records notes when a declared size or digest disagrees with
the inspected bytes.

## Storage

`EvidenceStore` keeps records in a canonical map with hash and tag indexes that
are updated on every mutation. It offers CRUD, `by_hash`, `by_tag`, pagination,
index integrity checks, an inspection cache, custody entry tracking, and a
versioned export/import manifest (`redscribe.evidence-lab/v4`). `StoreStats`
exposes counts and a weak ETag for the current snapshot.

## API

`EvidenceApi` handlers return v4 envelopes via `ok` / `fail`. Each handler
first checks the `EVIDENCE_LAB` feature gate and then the required capability
(`read`, `write`, or `export`). Routes:

- `GET /api/v4/evidence` — paginated list with cursor, tag filter, and ETag.
- `POST /api/v4/evidence` — create a record; optional `bytes_hex` is hashed.
- `GET /api/v4/evidence/{id}` — one record.
- `GET /api/v4/evidence/{id}/inspect` — cached or freshly built inspection.
- `GET /api/v4/evidence/{id}/custody` — entries plus chain verification.
- `GET /api/v4/evidence-manifest` — exported manifest.

Creation emits `EVIDENCE_ADDED` and, when bytes are supplied,
`EVIDENCE_HASHED` through the shared `EventBus`. All client-input failures are
converted into `ApiError` envelopes with stable `ErrorCode` values.

## Frontend

The `EvidenceLab` component keeps its state in `evidenceLabReducer` and loads
data through `EvidenceLabClientV4`, which wraps the shared `V4Client`. The UI
has an evidence list, a hex grid with offset/hex/ascii columns, a strings panel
with a minimum-length control, a hash verification badge, and a custody
timeline with a chain-integrity banner. Styles import `tokens-v4.css` and use
only `var(--v4-*)` tokens, including reduced-motion and narrow-screen rules.

## Verification

Run the standard gates:

```sh
python3 scripts/loc_gate.py --baseline 9f0459cf510def70e9e78f08b54ec86795c246be \
  --min-added 2500 --min-net 2500 --min-test-loc 400
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
cd frontend && npm test && npm run format:check && npm run typecheck && npm run build
```
