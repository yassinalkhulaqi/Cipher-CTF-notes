# Vault Portability V3

The V3 portability feature makes vault movement safe, verifiable, and
conflict-free. Two independently edited vaults can be exported, compared, and
merged with every difference explained and every decision audited.

The implementation is additive:

- Backend domain: `redscribe.v3.portability`
- API namespace: `redscribe.v3.namespaces.sync`
- Frontend feature: `frontend/src/features/portability`
- Tests: `tests/v3_portability/` and `frontend/scripts/portability-v3.test.ts`

No B00 entity, event, or API contract is redefined. The package composes the
universal `EntityRecord`, `EntityId`, `EntityLink`, `DomainEvent`, `EventBus`,
`V3Config`, and `V3Router` contracts from the platform kernel.

## Design goals

1. **Encrypted at rest in transit.** A portable bundle is a JSON envelope with
   an authenticated ciphertext body. Passphrases never appear in manifests,
   receipts, logs, or error envelopes.
2. **Causal comparison.** Version vectors record per-device logical clocks so a
   merge can distinguish a fast-forward from a genuine concurrent edit.
3. **Explainable conflicts.** Every unresolved difference carries a stable
   reason code, a human description, and field-level diffs suitable for a
   side-by-side workbench.
4. **No silent data loss.** A merge never guesses when both sides edited the
   same field; the caller must record a decision.
5. **Resumable movement.** Chunked transfers keep per-chunk receipts so an
   interrupted transfer can resume without re-sending received data.
6. **Auditable outcomes.** Conflict decisions form a hash-chained ledger, and a
   verification receipt records every integrity check performed on a bundle.

## Backend modules

| Module | Responsibility |
| --- | --- |
| `errors.py` | Stable error taxonomy and machine codes for API mapping. |
| `crypto.py` | PBKDF2 key derivation, BLAKE2b keystream, HMAC-SHA256 authentication, base64 blob encoding. |
| `canonical.py` | Deterministic JSON canonicalization and SHA-256 digest helpers. |
| `vectors.py` | Version vectors, causal comparison, merge, dominance, serialization. |
| `device.py` | Device identity, fingerprints, trust registry, and origin seals. |
| `records.py` | Portable entity snapshots wrapping `EntityRecord`, plus link serialization. |
| `manifest.py` | Bundle manifests, per-record checksums, payload digests, verification reports. |
| `merge.py` | Three-way merge for entity families, link merge, field diffs, reason codes, resolution application. |
| `conflicts.py` | Resolution choices, hash-chained decision ledger, redacted event emission. |
| `bundle.py` | Bundle creation, encryption, parsing, inspection, local file I/O. |
| `transfer.py` | Chunked transfer sessions, checksums, pause/resume/cancel/finish. |
| `dryrun.py` | Dry-run change previews for merges, imports, and bundle creation. |
| `receipt.py` | Verification receipts with named checks and plain-text rendering. |
| `service.py` | `PortabilityService` facade coordinating all of the above. |

## Encryption format

`EncryptedBlob` is versioned with algorithm `blake2b-xor-hmac-sha256-v1`.

- A 32-byte master key is derived with `hashlib.pbkdf2_hmac` using a 16-byte
  random salt and a configurable iteration count.
- Separate purpose-bound keys are derived from the master with BLAKE2b
  personalization strings for encryption and authentication.
- The keystream is BLAKE2b(key, nonce || big-endian counter) blocks XORed with
  the plaintext. A fresh 16-byte nonce is generated per bundle.
- An HMAC-SHA256 tag covers `nonce || length || ciphertext || aad`, where the
  additional authenticated data binds the blob to the bundle id, manifest
  digest, and authoring device fingerprint.
- Decryption verifies the tag with `hmac.compare_digest` before returning any
  plaintext, so a wrong passphrase or tampered field fails closed.

This construction uses only the standard library. It is intended for local,
offline vault portability; it is not a replacement for a audited general-purpose
encryption library when one becomes available.

## Version vectors

A `VersionVector` is an immutable map of device name to non-negative counter.

| Comparison | Meaning | Merge action |
| --- | --- | --- |
| `equal` | Both sides know the same events | No change |
| `left_ahead` | Local vector dominates incoming | Fast-forward local |
| `right_ahead` | Incoming vector dominates local | Fast-forward incoming |
| `concurrent` | Each side saw events the other did not | Field-level three-way merge |

Vectors merge by component-wise maximum. A vector that does not dominate the
recorded common ancestor produces a `vector_regression` conflict rather than a
silent overwrite.

## Three-way merge

`merge_families(base, local, remote)` groups records by canonical entity
reference and merges each group independently. Entity families come from the
universal `EntityKind` values, so a branch can add a kind without touching the
merge engine.

For one reference:

1. **Only one side present** — apply that side (or accept a deletion).
2. **Both sides identical** — no change.
3. **One side unchanged relative to the ancestor** — apply the other side.
4. **Both changed disjoint fields** — combine the changes and merge vectors.
5. **Both changed the same field** — emit a conflict with a reason code and a
   field-level diff.
6. **Delete versus edit** — emit a `delete_modify` conflict; deletion never
   silently wins.
7. **Two unrelated additions with the same id** — emit `concurrent_add`.

Typed links are merged separately. Links whose endpoints are missing from the
merged set are reported with `link_target_missing` instead of being written.

### Conflict reason codes

| Code | Meaning | Severity |
| --- | --- | --- |
| `field_both_edited` | Same scalar field edited on both sides | error |
| `delete_modify` | One side deleted, the other edited | critical |
| `concurrent_add` | Same id created independently | critical |
| `tag_set_divergence` | Tag sets changed differently | error |
| `content_divergence` | Note body changed differently | error |
| `link_target_missing` | Link endpoint absent from the merge | error |
| `vector_regression` | Incoming vector lost known history | error |
| `schema_mismatch` | Bundle schema unsupported | warning |
| `checksum_mismatch` | Record digest differs from manifest | warning |
| `unknown_field` | Unrecognized payload field | error |

## Resolution and audit

`ConflictResolver.resolve()` applies a `ResolutionChoice` (`keep_local`,
`keep_remote`, `merge_fields`, or `skip`) and records a `ResolutionEntry` in a
hash-chained `ResolutionLedger`. Each entry stores the pre- and post-decision
digests, the actor and device, and an optional note. `verify_chain()` detects
edits to any recorded decision.

Events are emitted through the shared `EventBus` with a `RedactionPolicy`
applied first. Secrets, tokens, and flag-shaped strings in notes never reach an
event payload, audit entry, or API error.

## Transfer lifecycle

`TransferManager.start()` splits bundle bytes into fixed-size chunks and stores
a digest per chunk. `push()` verifies each chunk before accepting it.

- `active` — receiving chunks.
- `paused` / `failed` — resumable; received chunks are preserved.
- `complete` — all chunks assembled and the final bundle digest verified.
- `cancelled` — terminal; cannot be resumed or pushed to.

`checkpoint()` returns received chunk indexes and outstanding chunk positions,
which is what the frontend progress view renders.

## Verification receipts

`build_receipt()` records six named checks:

1. `manifest_structure` — manifest version and counts are coherent.
2. `payload_checksums` — every entity matches its manifest checksum.
3. `payload_digest` — the collection digest matches the manifest.
4. `authentication_tag` — HMAC verification succeeded during open.
5. `device_origin` — the authoring device is known and trusted.
6. `conflict_decisions` — every merge decision was audited.

A receipt can be rendered to plain text with `VerificationReceipt.render()` and
archived from the UI.

## API namespace

Routes are registered dynamically with `router.add("sync", action, handler)`;
there is no central dispatch table to edit. `V3Router.install_namespaces()`
discovers the module automatically.

| Action | Purpose | Notable fields |
| --- | --- | --- |
| `sync.health` | Capabilities and catalogs | — |
| `sync.reasons` | Reason codes and strategies | — |
| `sync.devices` | Device registry | — |
| `sync.device.register` | Register a device | `device_id`, `label` |
| `sync.device.trust` | Trust a device | `device_id` |
| `sync.vectors.compare` | Compare vectors | `local`, `remote` |
| `sync.bundle.plan` | Preview bundle contents | `entities`, `links` |
| `sync.bundle.create` | Seal an encrypted bundle | `passphrase`, `entities` |
| `sync.bundle.inspect` | Metadata without a key | `bundle_id` |
| `sync.bundle.open` | Verified plaintext view | `bundle_id`, `passphrase` |
| `sync.bundle.verify` | Open and issue a receipt | `bundle_id`, `passphrase` |
| `sync.conflicts.detect` | Detect and group conflicts | `base`, `local`, `remote` |
| `sync.merge.preview` | Store a dry-run import | `bundle_id`, `passphrase`, `base`, `local` |
| `sync.conflicts.resolve` | Apply auditable decisions | `preview_id`, `decisions` |
| `sync.receipt.get` / `sync.receipt.list` | Retrieve receipts | `receipt_id` |
| `sync.audit.list` | Redacted audit trail | — |
| `sync.transfer.start` | Begin chunked transfer | `bundle_id`, `chunk_size` |
| `sync.transfer.status` / `sync.transfer.checkpoint` | Inspect progress | `transfer_id` |
| `sync.transfer.chunk` | Receive one chunk | `transfer_id`, `index`, `chunk` |
| `sync.transfer.pause` / `resume` / `cancel` / `finish` | Lifecycle controls | `transfer_id` |

Failures map to stable V3 codes: verification and transfer errors become
`precondition_failed`, decryption and device errors become `forbidden`, and
merge/resolution errors become `conflict`.

## Frontend feature

- **Bundle wizard** — six-step indicator, family chips, passphrase strength
  meter, validation messages, and scope toggles.
- **Dry-run preview** — action counts, vector relation, warnings, and a change
  table before anything is written.
- **Conflict workbench** — filter by reason or text, side-by-side ancestor /
  local / incoming diff, strategy defaults, and one-click decisions per
  conflict.
- **Transfer progress** — progress bar, outstanding chunk list, and cancel /
  resume controls derived from transfer state.
- **Verification receipt** — check list with pass/fail marks, digest summary,
  and an archived plain-text view.

Styles live in `frontend/src/features/portability/portability.css` and use V3
design tokens. No shared stylesheet or `main.tsx` is edited.

## Tests and exit criteria

Python tests cover encryption round-trips, wrong-key refusal, tamper detection,
version-vector ordering, manifest verification reason codes, every three-way
merge case, link conflicts, ledger integrity, redacted events, bundle file
round-trips, interrupted transfer resume, capability gating, and namespace
dispatch. Frontend tests cover pure helpers, reducer transitions, request
builders, typed client calls, and error mapping.

**Exit criterion:** two independently edited vaults can be merged with every
conflict explained, every decision audited, and no data lost.
