# Security Vault (v4)

The v4 security vault provides end-to-end local encryption, key lifecycle
management, single-use recovery, nested redaction, and a privacy-aware
dashboard. It has no external dependencies: confidentiality and integrity are
built from `hashlib.sha256` and `hmac` in the Python standard library.

## Scope and invariants

- Everything runs locally. No network calls, shell execution, or dynamic code
  evaluation occurs anywhere in the feature.
- Raw key material, passphrases, and plaintext recovery codes are **never**
  persisted and never emitted in events, API responses, or logs.
- `KeyMetadataStore.assert_secret_free()` walks every persisted value and
  rejects secret-shaped field names before the store can be handed onward.
- Event payloads are built from an explicit allowlist and then passed through
  the shared `default_redactor`, so a future payload addition cannot leak a
  passphrase by accident.

## Threat model

| Threat | Mitigation |
| --- | --- |
| Ciphertext tampering | HMAC-SHA256 over nonce, ciphertext, and length-prefixed AAD |
| Wrong key or context | MAC verification happens before decryption; AAD is authenticated |
| Nonce reuse | Unique nonce per seal from an injectable nonce source |
| Key compromise | Versioned rotation; retired keys can open but not seal; revocation removes resident material |
| Recovery code replay | Only SHA-256 digests are stored; codes are single-use |
| Secret leakage via telemetry | Allowlisted, redacted event payloads; no key bytes in status responses |
| Mass redaction bypass | Dotted paths with `*` wildcards plus a global LOCKED mode |

## Data contracts (`types.py`)

- `KeyRecord` — opaque id, version, `KeyState`, `created_at`, `rotated_at`. It
  deliberately has no field that can hold key bytes.
- `KeySaltRecord` — non-secret PBKDF2 parameters; safe to persist with metadata.
- `SealedEnvelope` — version, key id, nonce, hex ciphertext, hex MAC, and AAD.
  All fields validate on construction and round-trip through `to_dict()`
  / `from_dict()`.
- `RecoveryCode` — id, digest, `used` flag, creation timestamp. `matches()`
  compares digests in constant time.
- `PrivacyMode` — `NORMAL`, `REDACTED`, `LOCKED`.
- `RedactionRule` — a dotted field path and a fixed replacement token.

## Services (`service.py`)

### StreamSeal

A SHA-256 counter-mode keystream XORed with the plaintext, followed by an
HMAC-SHA256 tag. Domain-separation constants keep the KDF, MAC, and AAD
contexts distinct. `seal()` accepts an injectable nonce source for
deterministic tests; `seal_for()` binds the envelope to a key id. `open()`
verifies the MAC with `hmac.compare_digest()` before decrypting, raising
`IntegrityError` on any mismatch. `rewrap()`, `seal_json()`, and `open_json()`
provide higher-level composition.

### KeyManager

- `derive_key()` uses PBKDF2-HMAC-SHA256 with a 16-byte salt and a 32-byte
  output. Derivation is deterministic for identical inputs.
- `initialize()` creates version 1 and stores only descriptors and salts.
- `rotate()` marks the current key `ROTATED` and installs the next version.
- `revoke()` marks a retired key `REVOKED` and discards resident material.
- A SHA-256 verifier digest allows `verify_passphrase()` and `restore()` to
  work across a lock/unlock cycle without storing the key itself.
- `fingerprint()` returns a short digest suitable for UI display.

### RecoveryManager

Generates single-use codes, stores only their digests, and consumes them
atomically through the metadata store. `invalidate_all()` retires outstanding
codes, for example after a rotation.

### Redactor

Recursively clones nested mappings and lists. Exact dotted paths and `*`
wildcards select fields to replace. NORMAL preserves data, REDACTED applies
rules, and LOCKED replaces every leaf. `redact_with_report()` returns the
changed paths for audit UI.

## Storage (`storage.py`)

`KeyMetadataStore` is an in-memory adapter with typed CRUD, version indexing,
recovery-digest indexing, JSON snapshots, SQLite row projections, and the
three-table `SCHEMA` DDL. Reads return immutable records, so callers cannot
mutate stored state by aliasing.

## API (`api.py`)

`GET /api/v4/vault` returns a status envelope with posture, key version,
counts, and privacy mode. `POST /api/v4/vault` dispatches on `action`:
`initialize`, `seal`, `open`, `rotate`, `lock`, `unlock`, `privacy`, `redact`,
`recovery_generate`, `recovery_consume`, and `status`.

Every route requires `Capability.ENCRYPT` and returns v4 `ok()` / `fail()`
envelopes. Domain failures map to stable `ErrorCode` values. Successful
mutations emit `VAULT_LOCKED`, `VAULT_UNLOCKED`, or `KEY_ROTATED` through the
shared event bus with redacted, allowlisted payloads.

## Frontend (`frontend/src/features/security-vault/`)

`VaultPanel.tsx` is a React dashboard with four tabs:

- **posture** — score bar, capability checks, and algorithm label;
- **keys** — seal/open forms, envelope summary, and rotation/lock/unlock UX;
- **recovery** — one-time code generation and consumption;
- **privacy** — mode switch and a live nested-redaction preview.

`state.ts` holds a strict reducer with bounded notices and selectors.
`client.ts` wraps the shared `V4Client`, converts `V4ApiError` into
`VaultClientError`, and exposes typed methods for every action. Styling in
`security-vault.css` imports `tokens-v4.css` and uses only `var(--v4-*)`
tokens, including graphite theme, density, focus, and reduced-motion support.

## Verification

- Python: ruff check, ruff format check, strict mypy, pytest.
- Frontend: Prettier check, TypeScript strict typecheck, node:test suites,
  esbuild production build.
- LOC gate: `scripts/loc_gate.py --baseline 9f0459cf... --min-added 2500
  --min-net 2500 --min-test-loc 400`.
