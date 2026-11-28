"""Service tests for sealing, keys, recovery, redaction, and metadata storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

import pytest

from redscribe.v4.vault_security.service import (
    DEFAULT_REPLACEMENT,
    LOCKED_REPLACEMENT,
    IntegrityError,
    KeyManager,
    PassphraseError,
    PostureLevel,
    RecoveryError,
    RecoveryManager,
    RedactionError,
    Redactor,
    StreamSeal,
    VaultKeyError,
    score_posture,
)
from redscribe.v4.vault_security.storage import (
    SCHEMA,
    KeyMetadataStore,
    StorageError,
    _walk,
)
from redscribe.v4.vault_security.types import (
    ENVELOPE_VERSION,
    KEY_BYTES,
    NONCE_BYTES,
    KeyRecord,
    KeySaltRecord,
    KeyState,
    PrivacyMode,
    RecoveryCode,
    RedactionRule,
)

FIXED_TIME = "2026-03-01T00:00:00.000Z"
LATER_TIME = "2026-04-01T00:00:00.000Z"
PASSPHRASE = "correct horse battery staple"
NEW_PASSPHRASE = "another valid passphrase 42"
KEY = bytes(range(KEY_BYTES))
OTHER_KEY = bytes(range(KEY_BYTES))[::-1]


def fixed_clock() -> str:
    return FIXED_TIME


def fixed_nonce(size: int) -> bytes:
    return bytes((index + 7) % 256 for index in range(size))


def alternate_nonce(size: int) -> bytes:
    return bytes((index + 31) % 256 for index in range(size))


@pytest.fixture
def store() -> KeyMetadataStore:
    return KeyMetadataStore()


@pytest.fixture
def seal() -> StreamSeal:
    return StreamSeal(nonce_source=fixed_nonce)


@pytest.fixture
def manager(store: KeyMetadataStore) -> KeyManager:
    return KeyManager(store=store, clock=fixed_clock, nonce_source=fixed_nonce, iterations=1000)


@pytest.fixture
def recovery(store: KeyMetadataStore) -> RecoveryManager:
    return RecoveryManager(store=store, clock=fixed_clock)


@pytest.fixture
def active_key(manager: KeyManager) -> KeyRecord:
    return manager.initialize(PASSPHRASE)


@pytest.mark.parametrize("length", [0, 1, 31, 32, 33, 257])
def test_seal_open_round_trip(seal: StreamSeal, length: int) -> None:
    plaintext = bytes(index % 251 for index in range(length))
    envelope = seal.seal(plaintext, KEY, "context")
    assert envelope.version == ENVELOPE_VERSION
    assert envelope.plaintext_size == length
    assert envelope.nonce == fixed_nonce(NONCE_BYTES).hex()
    assert seal.open(envelope, KEY, "context") == plaintext
    assert seal.verify(envelope, KEY, "context")


def test_keystream_is_deterministic_and_domain_separated() -> None:
    first = StreamSeal.keystream(KEY, fixed_nonce(NONCE_BYTES), 64)
    second = StreamSeal.keystream(KEY, fixed_nonce(NONCE_BYTES), 64)
    assert first == second
    assert len(first) == 64
    assert first[:32] != first[32:]
    assert StreamSeal.keystream(OTHER_KEY, fixed_nonce(NONCE_BYTES), 32) != first[:32]
    assert StreamSeal.keystream(KEY, fixed_nonce(NONCE_BYTES), 0) == b""
    with pytest.raises(VaultKeyError, match="keystream length must not be negative"):
        StreamSeal.keystream(KEY, fixed_nonce(NONCE_BYTES), -1)


def test_tampered_ciphertext_is_rejected(seal: StreamSeal) -> None:
    envelope = seal.seal(b"vault note", KEY, "note:1")
    raw = bytearray(envelope.ciphertext)
    raw[0] ^= 0x01
    tampered = replace(envelope, ciphertext_hex=bytes(raw).hex())
    with pytest.raises(IntegrityError, match="mac mismatch"):
        seal.open(tampered, KEY, "note:1")
    assert not seal.verify(tampered, KEY, "note:1")


def test_tampered_mac_is_rejected(seal: StreamSeal) -> None:
    envelope = seal.seal(b"vault note", KEY)
    bad_mac = ("00" if envelope.mac_hex[:2] != "00" else "ff") + envelope.mac_hex[2:]
    with pytest.raises(IntegrityError, match="mac mismatch"):
        seal.open(replace(envelope, mac_hex=bad_mac), KEY)


def test_wrong_key_and_aad_are_rejected(seal: StreamSeal) -> None:
    envelope = seal.seal(b"secret payload", KEY, "owner:a")
    with pytest.raises(IntegrityError, match="mac mismatch"):
        seal.open(envelope, OTHER_KEY, "owner:a")
    with pytest.raises(IntegrityError, match="mac mismatch"):
        seal.open(envelope, KEY, "owner:b")


def test_tampered_nonce_and_version_are_rejected(seal: StreamSeal) -> None:
    envelope = seal.seal(b"payload", KEY)
    with pytest.raises(IntegrityError, match="mac mismatch"):
        seal.open(replace(envelope, nonce=alternate_nonce(NONCE_BYTES).hex()), KEY)
    with pytest.raises(IntegrityError, match="unsupported envelope version"):
        seal.open(replace(envelope, version=99), KEY)


def test_invalid_keys_and_nonce_sources(seal: StreamSeal) -> None:
    with pytest.raises(VaultKeyError, match="exactly 32 bytes"):
        seal.seal(b"data", b"short")
    with pytest.raises(VaultKeyError, match="key must be bytes"):
        StreamSeal.validate_key("text")  # type: ignore[arg-type]
    broken = StreamSeal(nonce_source=lambda _: b"short")
    with pytest.raises(VaultKeyError, match="invalid nonce"):
        broken.seal(b"data", KEY)


def test_rewrap_preserves_plaintext(seal: StreamSeal) -> None:
    envelope = seal.seal(b"rotate me", KEY, "ctx")
    moved = seal.rewrap(envelope, KEY, OTHER_KEY, "ctx")
    assert moved.key_id == ""
    assert seal.open(moved, OTHER_KEY, "ctx") == b"rotate me"
    assert not seal.verify(envelope, OTHER_KEY, "ctx")


def test_json_helpers(seal: StreamSeal) -> None:
    payload = {"z": 1, "a": {"nested": [True, None]}}
    envelope = seal.seal_json(payload, KEY, "json")
    assert seal.open_json(envelope, KEY, "json") == payload
    with pytest.raises(IntegrityError, match="mac mismatch"):
        seal.open_json(envelope, OTHER_KEY, "json")


def test_open_json_requires_object(seal: StreamSeal) -> None:
    envelope = seal.seal(b"[1,2,3]", KEY)
    with pytest.raises(IntegrityError, match="must be an object"):
        seal.open_json(envelope, KEY)


def test_scoped_seal_binds_key_id(manager: KeyManager, active_key: KeyRecord) -> None:
    seal = StreamSeal(nonce_source=fixed_nonce)
    envelope = seal.seal_for(b"bound", active_key.id, manager.current_key(), "ctx")
    assert envelope.key_id == active_key.id
    assert seal.open(envelope, manager.current_key(), "ctx") == b"bound"


def test_derive_key_is_deterministic(manager: KeyManager) -> None:
    salt = fixed_nonce(16)
    first = manager.derive_key(PASSPHRASE, salt, iterations=500)
    second = manager.derive_key(PASSPHRASE, salt, iterations=500)
    assert first == second
    assert len(first) == KEY_BYTES
    assert manager.derive_key(PASSPHRASE, salt, iterations=501) != first
    assert manager.derive_key(PASSPHRASE, alternate_nonce(16), iterations=500) != first
    assert manager.derive_key(NEW_PASSPHRASE, salt, iterations=500) != first
    assert hashlib.sha256(first).hexdigest() != first.hex()


def test_passphrase_validation(manager: KeyManager) -> None:
    with pytest.raises(PassphraseError, match="at least 12 characters"):
        manager.validate_passphrase("short")
    with pytest.raises(PassphraseError, match="salt must be exactly 16 bytes"):
        manager.derive_key(PASSPHRASE, b"tiny")
    with pytest.raises(PassphraseError, match="iterations must be positive"):
        manager.derive_key(PASSPHRASE, fixed_nonce(16), iterations=0)


def test_initialize_persists_metadata_only(
    manager: KeyManager, store: KeyMetadataStore, active_key: KeyRecord
) -> None:
    assert active_key.version == 1
    assert active_key.state is KeyState.ACTIVE
    assert active_key.created_at == FIXED_TIME
    assert manager.active() == active_key
    assert manager.version_index() == {1: active_key.id}
    assert manager.resident_count() == 1
    snapshot = json.dumps(store.snapshot())
    assert PASSPHRASE not in snapshot
    assert manager.current_key().hex() not in snapshot
    store.assert_secret_free()


def test_initialize_twice_fails(manager: KeyManager, active_key: KeyRecord) -> None:
    with pytest.raises(VaultKeyError, match="already has an active key"):
        manager.initialize(NEW_PASSPHRASE)


def test_rotation_retires_old_key_and_installs_new(
    manager: KeyManager, store: KeyMetadataStore, active_key: KeyRecord
) -> None:
    seal = StreamSeal(nonce_source=fixed_nonce)
    old_envelope = seal.seal_for(b"old", active_key.id, manager.current_key())
    result = manager.rotate(NEW_PASSPHRASE)
    assert result.previous.version == 1
    assert result.previous.rotated_at == FIXED_TIME
    assert result.current.version == 2
    assert result.current.state is KeyState.ACTIVE
    assert manager.version_index() == {1: active_key.id, 2: result.current.id}
    assert seal.open(old_envelope, manager.key_for(active_key.id)) == b"old"
    assert not seal.verify(old_envelope, manager.current_key())
    assert manager.verify_passphrase(result.current.id, NEW_PASSPHRASE)
    assert not manager.verify_passphrase(result.current.id, PASSPHRASE)
    store.assert_secret_free()


def test_revocation_blocks_opening(manager: KeyManager, active_key: KeyRecord) -> None:
    rotated = manager.rotate(NEW_PASSPHRASE)
    with pytest.raises(VaultKeyError, match="cannot revoke the active key"):
        manager.revoke(rotated.current.id)
    revoked = manager.revoke(active_key.id)
    assert revoked.state is KeyState.REVOKED
    with pytest.raises(VaultKeyError, match="cannot open envelopes"):
        manager.key_for(active_key.id)
    with pytest.raises(VaultKeyError, match="already revoked"):
        manager.revoke(active_key.id)


def test_forget_and_current_key_errors(manager: KeyManager, active_key: KeyRecord) -> None:
    assert manager.forget(active_key.id)
    assert not manager.forget(active_key.id)
    assert manager.resident_count() == 0
    assert manager.fingerprint(active_key.id) == "unavailable"
    with pytest.raises(VaultKeyError, match="not resident in memory"):
        manager.current_key()
    rotated = manager.rotate(NEW_PASSPHRASE)
    assert len(manager.fingerprint(rotated.current.id)) == 12


def test_missing_key_errors(manager: KeyManager) -> None:
    with pytest.raises(StorageError, match="unknown key"):
        manager.get("00000000-0000-0000-0000-000000000000")
    with pytest.raises(VaultKeyError, match="no active key"):
        manager.rotate(NEW_PASSPHRASE)
    with pytest.raises(VaultKeyError, match="no active key"):
        manager.current_key()


def test_recovery_codes_are_single_use(store: KeyMetadataStore, recovery: RecoveryManager) -> None:
    issued = recovery.generate(3)
    assert len(issued.codes) == 3
    assert all(code.upper().startswith("RS-") for code in issued.codes)
    assert all(not record.used for record in issued.records)
    assert PASSPHRASE not in json.dumps(store.snapshot())
    assert issued.codes[0] not in json.dumps(store.snapshot())
    assert recovery.verify(issued.codes[0]) == issued.records[0]
    consumed = recovery.consume(issued.codes[0])
    assert consumed.used
    assert recovery.verify(issued.codes[0]) is None
    assert len(recovery.remaining()) == 2
    with pytest.raises(RecoveryError, match="already used"):
        recovery.consume(issued.codes[0])
    with pytest.raises(RecoveryError, match="unknown recovery code"):
        recovery.consume("RS-0000000000-0000000000")


def test_recovery_normalization_and_digest(recovery: RecoveryManager) -> None:
    issued = recovery.generate(1)
    code = issued.codes[0]
    spaced = f"  {code[:2]} {code[2:].lower()}  "
    assert recovery.verify(spaced) == issued.records[0]
    assert RecoveryManager.digest(code) == hashlib.sha256(code.casefold().encode()).hexdigest()
    with pytest.raises(RecoveryError, match="too short"):
        RecoveryManager.normalize("tiny")


def test_recovery_invalid_counts_and_duplicate_sources(store: KeyMetadataStore) -> None:
    manager = RecoveryManager(store=store, clock=fixed_clock, code_source=lambda _: ["SAME"])
    with pytest.raises(RecoveryError, match="between 1 and 8"):
        manager.generate(0)
    with pytest.raises(RecoveryError, match="unique codes"):
        manager.generate(2)


def test_recovery_invalidate_all(recovery: RecoveryManager) -> None:
    recovery.generate(4)
    assert recovery.is_available()
    assert recovery.invalidate_all() == 4
    assert not recovery.is_available()
    assert recovery.invalidate_all() == 0


def nested_payload() -> dict[str, Any]:
    return {
        "title": "report",
        "credentials": {"api_key": "abc", "user": "alice"},
        "notes": [{"token": "xyz", "body": "visible"}, {"token": "pq"}],
        "empty": None,
    }


def test_redactor_nested_exact_and_wildcard_rules() -> None:
    redactor = Redactor()
    rules = [
        RedactionRule("credentials.api_key", "[secret]"),
        RedactionRule("notes.*.token", DEFAULT_REPLACEMENT),
    ]
    result = redactor.apply(nested_payload(), rules)
    assert result["credentials"] == {"api_key": "[secret]", "user": "alice"}
    assert result["notes"] == [
        {"token": DEFAULT_REPLACEMENT, "body": "visible"},
        {"token": DEFAULT_REPLACEMENT},
    ]
    assert result["title"] == "report"
    assert result["empty"] is None
    assert nested_payload()["credentials"]["api_key"] == "abc"


def test_redactor_modes_and_report() -> None:
    redactor = Redactor()
    normal = redactor.redact_with_report(
        nested_payload(), [RedactionRule("title", "[x]")], PrivacyMode.NORMAL
    )
    assert normal.data == nested_payload()
    assert normal.paths == ()
    assert normal.mode is PrivacyMode.NORMAL
    locked = redactor.redact_with_report(nested_payload(), (), PrivacyMode.LOCKED)
    assert locked.paths
    assert locked.data["credentials"] == {
        "api_key": LOCKED_REPLACEMENT,
        "user": LOCKED_REPLACEMENT,
    }
    assert locked.to_dict()["mode"] == "locked"
    redacted = redactor.redact_with_report(nested_payload(), [RedactionRule("title", "[x]")])
    assert redacted.paths == ("title",)


def test_redactor_rejects_invalid_inputs() -> None:
    redactor = Redactor()
    with pytest.raises(RedactionError, match="data must be a mapping"):
        redactor.apply(["not", "a", "mapping"])  # type: ignore[arg-type]
    with pytest.raises(RedactionError, match="mode must be a PrivacyMode"):
        redactor.apply({}, (), "locked")  # type: ignore[arg-type]
    with pytest.raises(RedactionError, match="rules must contain"):
        redactor.apply({}, ["bad"])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="default_replacement must not be empty"):
        Redactor("")


def test_posture_scoring(manager: KeyManager, active_key: KeyRecord) -> None:
    strong = score_posture(active_key, 2, PrivacyMode.REDACTED, manager.resident_count())
    assert strong.level is PostureLevel.STRONG
    assert strong.score == 100
    assert "active-key" in strong.checks
    assert strong.to_dict()["score"] == 100
    weak = score_posture(None, 0, PrivacyMode.NORMAL, 0)
    assert weak.level is PostureLevel.WEAK
    assert weak.score == 0
    fair = score_posture(active_key, 0, PrivacyMode.NORMAL, 1)
    assert fair.level is PostureLevel.FAIR
    assert fair.score == 60


def test_store_crud_and_version_index(store: KeyMetadataStore) -> None:
    first = KeyRecord("01234567-89ab-cdef-0123-456789abcdef", 1, KeyState.ACTIVE, FIXED_TIME)
    second = KeyRecord(
        "fedcba98-7654-3210-fedc-ba9876543210",
        2,
        KeyState.ROTATED,
        FIXED_TIME,
        LATER_TIME,
    )
    assert store.put_key(first) == first
    assert store.put_key(second) == second
    assert store.get_key(first.id) == first
    assert store.list_keys() == [first, second]
    assert store.keys_by_state(KeyState.ROTATED) == [second]
    assert store.active_key() == first
    assert store.version_index() == {1: first.id, 2: second.id}
    assert store.next_version() == 3
    assert len(store) == 2
    replaced = replace(second, state=KeyState.REVOKED)
    assert store.replace_key(replaced) == replaced
    assert store.delete_key(second.id) == replaced
    assert store.find_key(second.id) is None


def test_store_rejects_duplicates_and_missing(store: KeyMetadataStore) -> None:
    record = KeyRecord("01234567-89ab-cdef-0123-456789abcdef", 1, KeyState.ACTIVE, FIXED_TIME)
    store.put_key(record)
    with pytest.raises(StorageError, match="already stored"):
        store.put_key(record)
    with pytest.raises(StorageError, match="version already stored"):
        store.put_key(replace(record, id="fedcba98-7654-3210-fedc-ba9876543210"))
    with pytest.raises(StorageError, match="unknown key"):
        store.get_key("00000000-0000-0000-0000-000000000000")
    with pytest.raises(StorageError, match="unknown salt"):
        store.get_salt("00000000-0000-0000-0000-000000000000")
    with pytest.raises(StorageError, match="cannot store salt for unknown key"):
        store.put_salt(
            KeySaltRecord("00000000-0000-0000-0000-000000000000", "cd" * 16, 1, FIXED_TIME)
        )


def test_store_salts_recovery_and_rows(store: KeyMetadataStore) -> None:
    key_id = "01234567-89ab-cdef-0123-456789abcdef"
    store.put_key(KeyRecord(key_id, 1, KeyState.ACTIVE, FIXED_TIME))
    salt = KeySaltRecord(key_id, "cd" * 16, 500, FIXED_TIME)
    assert store.put_salt(salt) == salt
    assert store.get_salt(key_id) == salt
    with pytest.raises(StorageError, match="salt already stored"):
        store.put_salt(salt)
    digest = hashlib.sha256(b"code").hexdigest()
    record = RecoveryCode("fedcba98-7654-3210-fedc-ba9876543210", digest, False, FIXED_TIME)
    store.put_recovery(record)
    assert store.find_recovery_by_hash(digest.upper()) == record
    assert store.mark_recovery_used(record.id).used
    assert not store.remaining_recovery()
    assert store.delete_recovery(record.id).id == record.id
    rows = store.to_rows()
    assert set(rows) == {"vault_keys", "vault_key_salts", "vault_recovery_codes"}
    assert len(rows["vault_keys"]) == 1
    assert len(SCHEMA) == 3
    assert store.clear_recovery() == 0
    store.clear()
    assert len(store) == 0


def test_store_secret_guard() -> None:
    with pytest.raises(StorageError, match=r"secret-shaped field at snapshot\.creds\.passphrase"):
        _walk({"creds": {"passphrase": "hunter2"}}, "snapshot")
    with pytest.raises(StorageError, match="secret-shaped field"):
        _walk({"items": [{"token": "abc"}]}, "snapshot")
    with pytest.raises(StorageError, match="unsupported value type"):
        _walk({"bytes": b"raw"}, "snapshot")
    _walk({"safe": {"code_hash": "ab" * 32}}, "snapshot")
