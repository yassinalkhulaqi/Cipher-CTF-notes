# V3 Vault Security Lifecycle (B10)

Branch `dev/v3-10-security-vault` turns the V3 evidence vault into a complete
security lifecycle: encryption at rest, key derivation and rotation, single-use
recovery, a redaction/consent policy engine, a redacted audit trail, and a
posture score that never exposes secret values. Everything runs locally with
the Python standard library (`hashlib`/`hmac`) and the B00 entity, event, and
API envelopes. No runtime dependency, network call, or code execution path is
introduced.

## 1. Layout

| Area | Files |
| --- | --- |
| Crypto and key state | `src/redscribe/v3/vault_security/crypto.py`, `keyring.py` |
| Recovery and policy | `src/redscribe/v3/vault_security/recovery.py`, `policy.py` |
| Audit and posture | `src/redscribe/v3/vault_security/audit.py`, `posture.py` |
| Orchestration | `src/redscribe/v3/vault_security/service.py` |
| API | `src/redscribe/v3/namespaces/security.py` |
| UI | `frontend/src/features/vault-security/` |
| Tests | `tests/v3_vault_security/`, `frontend/scripts/vault-security-v3.test.ts` |

B00 contracts are reused, not redefined: event subjects are `EntityId` values
built from `ENTITY_EVIDENCE`; events are `DomainEvent` records published on
`EventBus`; audit detail redaction delegates to `redact_payload`/`redact_text`
in `redscribe.v3.events.redaction`; all routes are registered through
`V3Router.add("security", action, handler)`.

## 2. Cryptographic design

`VaultSeal` is a self-describing JSON envelope (`magic = RSV3VAULT`,
`version = 1`) containing a random 16-byte salt, a random 16-byte nonce,
base64url ciphertext, an HMAC-SHA256 tag, and public KDF parameters.

1. `derive_vault_key(passphrase, salt, params)` uses
   `hashlib.pbkdf2_hmac("sha256", ..., iterations, dklen=64)`. Default is
   120,000 iterations; the minimum accepted is 10,000 and the posture floor is
   100,000. The 64-byte result is split into a 32-byte stream key and a
   32-byte MAC key.
2. Confidentiality is an HMAC-SHA256 counter-mode keystream; integrity is a
   separate HMAC over the format header, nonce, and ciphertext. The nonce is
   bound to the vault id and optional associated data with SHA-256, so a seal
   from one vault cannot be replayed into another.
3. Decryption verifies the tag with `hmac.compare_digest` before producing any
   plaintext. Wrong keys and tampered seals raise `VaultIntegrityError`.
4. `verify_vault_passphrase` recomputes only the tag, so a passphrase can be
   checked without exposing content.

The key ring stores only `KeyDescriptor` metadata and a BLAKE2b verifier of
the derived key — never the passphrase or the raw key. `KeyRing.__repr__` omits
the in-memory passphrase so tracebacks cannot leak it. Rotation creates a new
active generation, retires the old one, and reseals content.

## 3. Lifecycle

A vault moves through `uninitialized → locked → unlocked → locked`.

1. **Setup.** `setup(passphrase, content, recovery_count, params)` installs the
   first key, seals JSON content, issues recovery codes, and immediately locks
   the vault. The response is the only time recovery codes are visible.
2. **Unlock.** `unlock(passphrase)` verifies the key, authenticates the seal,
   and exposes a defensive copy of the content in memory. A failed attempt is
   recorded as `vault.access.denied` and raises `InvalidPassphraseError` with a
   generic message.
3. **Work.** `content()` and `replace_content()` operate only while unlocked;
   `require_unlocked()` raises `VaultLockedError` otherwise. Content is never
   written in plaintext.
4. **Rotate.** `rotate(new_passphrase)` requires an unlocked vault. It derives
   a new key, reseals the same content, retires the previous generation, and
   issues a fresh recovery batch — old codes stop working on purpose.
5. **Lock.** `lock()` clears plaintext content and forgets the passphrase.
6. **Recover.** Each issued code is wrapped as an escrow: the current
   passphrase is encrypted under the normalized code. `recover(code,
   new_passphrase)` consumes the code (single-use, even if a later step fails),
   unwraps the old passphrase, opens the seal, resets the key ring, reseals with
   the new passphrase, replaces every other code, and returns to `locked`.
   Codes are stored only as salted SHA-256 digests; the plaintext is shown once.

### Documented steps for a fresh vault

```python
from redscribe.v3.vault_security import VaultSecurityService

vault = VaultSecurityService(vault_id="case-1")
result = vault.setup("a long unique passphrase", content={"notes": []})
print(result.recovery_codes)  # save offline; never shown again
vault.unlock("a long unique passphrase")
vault.replace_content({"notes": [{"id": "n1"}]})
vault.rotate("a new long passphrase")
vault.lock()
vault.recover(result.recovery_codes[0], "a recovered passphrase")
```

The same flow is available through the API routes below and through the React
setup wizard and recovery flow.

## 4. Policy engine

`PolicyEngine` combines named regex detectors with precedence-ordered rules.

- Built-ins cover AWS keys, GitHub tokens, PEM private keys, assigned
  passwords, bearer tokens, JWTs, and CTF flags. Detectors return `SecretMatch`
  records containing offsets and classification — never the matched value.
- `PolicyRule` overrides choose `mask` (default), `hash` (12-hex digest of the
  match), or `remove`. Precedence is highest `priority`, then lexicographically
  smallest `rule_id`; a `*` rule applies to every pattern. Disabled rules and
  patterns are ignored. Ships with mandatory removal of private key blocks and
  masking of flags.
- `ConsentRegistry` tracks explicit grants for `export_plaintext`,
  `share_external`, `ai_assist`, and `log_content`. Scopes with secrets and no
  grant return `requires_consent=True, allowed=False`; `log_content` is always
  allowed but forced through redaction.
- `assert_clean` raises if serialized content matches any detector. The
  service calls it on every event payload, audit export, and posture report.

## 5. Audit and posture

`AuditTrail.record` sanitizes detail recursively with the B00 redactor and the
active policy redactor before appending an immutable `AuditEntry`. Exports are
JSON or JSONL; `AuditFilter` supports action, outcome, actor, subject, time
window, request id, and pagination. Secret-shaped values in exported text fail
a final `assert_clean` check and the export is refused.

`score_posture` builds ten checks (encryption, locked-by-default, KDF strength,
key freshness, recovery availability and freshness, detectors, redaction rules,
plaintext-export consent, and audit presence). The report contains only ids,
labels, pass/fail, weights, and static remediation text; `contains_secrets` is
always `False` and `assert_secret_free` verifies the serialized report against
the policy engine. Bands: `strong ≥ 85`, `fair ≥ 70`, `weak ≥ 50`, otherwise
`critical`.

## 6. API routes

All routes are `POST /api/v3/security/<action>` and return the V3 envelope.

| Action | Purpose |
| --- | --- |
| `status`, `posture` | Secret-free dashboard state (public) |
| `setup`, `unlock`, `lock`, `rotate` | Core lifecycle |
| `recovery_issue`, `recover` | Code issuance and single-use recovery |
| `policy_get`, `policy_update`, `policy_preview` | Policy and safe previews |
| `audit_list`, `audit_export`, `events` | Redacted history and event stream |

Errors use B00 `V3ErrorCode`: `forbidden` for verification failures,
`precondition_failed` for locked/uninitialized state, `conflict` for double
setup, and `invalid_request` for policy/payload errors. Error messages never
echo passphrases, codes, or detected secrets.

## 7. Frontend

`frontend/src/features/vault-security/` ships a posture dashboard, a
setup/rotation wizard, a recovery flow with an explicit confirmation checkbox,
a policy editor, and an audit viewer with filters and locked states. Locked
views show `Vault locked - unlock to view content` and never render content.
Recovery codes are masked until explicitly revealed and are never sent back to
the API except at redemption. Styling lives in `vault-security.css`; no shared
stylesheet or `main.tsx` is edited.

## 8. Verification

```sh
PYTHONPATH=src python3 -m pytest -q -p no:asyncio tests/v3_vault_security/
cd frontend && REDSCRIBE_SKIP_TYPECHECK=1 npm test
python3 scripts/loc_gate.py --baseline c65e699 --min-net 2000 --min-test-loc 600
PYTHONPATH=src python3 -m ruff check .
PYTHONPATH=src python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
```

Covered contracts: encrypt/decrypt round trip, wrong-key and tamper refusal,
vault-id binding, rotation preserving data, single-use recovery and replay
rejection, policy precedence and consent gating, recursive audit redaction, and
no-secret assertions across logs, events, errors, exports, and posture output.
