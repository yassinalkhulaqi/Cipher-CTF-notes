"""Contract tests for the secret-free v4 vault data types."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

import pytest

from redscribe.v4.vault_security.types import (
    ENVELOPE_VERSION,
    KEY_BYTES,
    MAC_BYTES,
    NONCE_BYTES,
    SALT_BYTES,
    KeyRecord,
    KeySaltRecord,
    KeyState,
    PrivacyMode,
    RecoveryCode,
    RedactionRule,
    SealedEnvelope,
    normalize_hex,
    normalize_timestamp,
    require_bool,
    require_identifier,
    require_positive_int,
    require_text,
)

CREATED = "2026-01-02T03:04:05.000Z"
ROTATED = "2026-02-03T04:05:06.000Z"
KEY_ID = "01234567-89ab-cdef-0123-456789abcdef"
OTHER_ID = "fedcba98-7654-3210-fedc-ba9876543210"
DIGEST = "ab" * 32


def test_key_state_parsing_is_case_insensitive() -> None:
    assert KeyState.parse("active") is KeyState.ACTIVE
    assert KeyState.parse("  RoTaTeD ") is KeyState.ROTATED
    assert KeyState.parse("revoked") is KeyState.REVOKED
    assert KeyState.ACTIVE.label == "Active"
    with pytest.raises(ValueError, match="Unknown key state"):
        KeyState.parse("dormant")


def test_key_state_capabilities() -> None:
    assert KeyState.ACTIVE.can_seal
    assert KeyState.ACTIVE.can_open
    assert not KeyState.ROTATED.can_seal
    assert KeyState.ROTATED.can_open
    assert not KeyState.REVOKED.can_open


def test_privacy_modes() -> None:
    assert PrivacyMode.parse("NORMAL") is PrivacyMode.NORMAL
    assert PrivacyMode.parse(" redacted ") is PrivacyMode.REDACTED
    assert PrivacyMode.parse("locked") is PrivacyMode.LOCKED
    assert PrivacyMode.NORMAL.label == "Normal"
    assert not PrivacyMode.NORMAL.hides_content
    assert PrivacyMode.REDACTED.hides_content
    assert PrivacyMode.LOCKED.hides_content
    with pytest.raises(ValueError, match="Unknown privacy mode"):
        PrivacyMode.parse("invisible")


def test_key_record_has_no_key_material_field() -> None:
    names = {item.name for item in fields(KeyRecord)}
    assert names == {"id", "version", "state", "created_at", "rotated_at"}
    assert not any("key" in name and name != "id" for name in names)


def test_key_record_round_trip() -> None:
    record = KeyRecord(
        id=KEY_ID,
        version=2,
        state=KeyState.ROTATED,
        created_at=CREATED,
        rotated_at=ROTATED,
    )
    payload = record.to_dict()
    assert payload == {
        "id": KEY_ID,
        "version": 2,
        "state": "rotated",
        "created_at": CREATED,
        "rotated_at": ROTATED,
    }
    assert KeyRecord.from_dict(payload) == record
    assert record.label == "v2 (Rotated)"
    assert record.is_usable


def test_active_key_record_allows_empty_rotated_at() -> None:
    record = KeyRecord(KEY_ID, 1, KeyState.ACTIVE, CREATED)
    assert record.rotated_at == ""
    assert record.is_usable
    assert KeyRecord.from_dict(record.to_dict()) == record


def test_retired_key_requires_rotated_at() -> None:
    with pytest.raises(ValueError, match="rotated_at is required"):
        KeyRecord(KEY_ID, 1, KeyState.REVOKED, CREATED)


def test_key_record_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="id must not be empty"):
        KeyRecord("", 1, KeyState.ACTIVE, CREATED)
    with pytest.raises(ValueError, match="id has an invalid shape"):
        KeyRecord("not-an-id", 1, KeyState.ACTIVE, CREATED)
    with pytest.raises(ValueError, match="version must be a positive integer"):
        KeyRecord(KEY_ID, 0, KeyState.ACTIVE, CREATED)
    with pytest.raises(ValueError, match="state must be a KeyState"):
        KeyRecord(KEY_ID, 1, "active", CREATED)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="created_at must be an ISO-8601"):
        KeyRecord(KEY_ID, 1, KeyState.ACTIVE, "yesterday")


def test_envelope_round_trip() -> None:
    envelope = SealedEnvelope(
        version=ENVELOPE_VERSION,
        key_id=KEY_ID,
        nonce="aa" * NONCE_BYTES,
        ciphertext_hex="bbccdd",
        mac_hex="ee" * MAC_BYTES,
        aad="note:42",
    )
    payload = envelope.to_dict()
    assert payload["version"] == 1
    assert SealedEnvelope.from_dict(payload) == envelope
    assert envelope.nonce_bytes == bytes.fromhex("aa" * NONCE_BYTES)
    assert envelope.ciphertext == bytes.fromhex("bbccdd")
    assert envelope.mac == bytes.fromhex("ee" * MAC_BYTES)
    assert envelope.plaintext_size == 3


def test_envelope_allows_empty_ciphertext_and_aad() -> None:
    envelope = SealedEnvelope(1, KEY_ID, "11" * NONCE_BYTES, "", "22" * MAC_BYTES, "")
    assert envelope.plaintext_size == 0
    assert envelope.aad == ""
    assert SealedEnvelope.from_dict(envelope.to_dict()) == envelope


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("nonce", "aa", "exactly 16 bytes"),
        ("mac_hex", "zz" * MAC_BYTES, "even-length hexadecimal"),
        ("ciphertext_hex", "abc", "even-length hexadecimal"),
        ("key_id", "bad id!", "invalid shape"),
    ],
)
def test_envelope_rejects_malformed_fields(field: str, value: str, message: str) -> None:
    values: dict[str, Any] = {
        "version": 1,
        "key_id": KEY_ID,
        "nonce": "aa" * NONCE_BYTES,
        "ciphertext_hex": "bb",
        "mac_hex": "cc" * MAC_BYTES,
        "aad": "",
    }
    values[field] = value
    with pytest.raises(ValueError, match=message):
        SealedEnvelope.from_dict(values)


def test_recovery_code_round_trip_and_matching() -> None:
    record = RecoveryCode(KEY_ID, DIGEST, False, CREATED)
    assert record.to_dict() == {
        "id": KEY_ID,
        "code_hash": DIGEST,
        "used": False,
        "created_at": CREATED,
    }
    assert RecoveryCode.from_dict(record.to_dict()) == record
    assert record.matches(DIGEST.upper())
    assert not record.matches("00" * 32)


def test_recovery_code_validation() -> None:
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        RecoveryCode(KEY_ID, "abcd", False, CREATED)
    with pytest.raises(ValueError, match="used must be a boolean"):
        RecoveryCode(KEY_ID, DIGEST, "no", CREATED)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="used must be a boolean"):
        RecoveryCode.from_dict({"id": KEY_ID, "code_hash": DIGEST, "used": "yes"})


def test_key_salt_record_round_trip() -> None:
    record = KeySaltRecord(KEY_ID, "cd" * SALT_BYTES, 1000, CREATED)
    assert record.salt == bytes.fromhex("cd" * SALT_BYTES)
    assert KeySaltRecord.from_dict(record.to_dict()) == record
    with pytest.raises(ValueError, match="exactly 16 bytes"):
        KeySaltRecord(KEY_ID, "cd", 1000, CREATED)
    with pytest.raises(ValueError, match="iterations must be a positive integer"):
        KeySaltRecord(KEY_ID, "cd" * SALT_BYTES, 0, CREATED)


def test_redaction_rule_paths() -> None:
    rule = RedactionRule("credentials.api_key", "[secret]")
    assert rule.segments == ("credentials", "api_key")
    assert rule.to_dict() == {"field": "credentials.api_key", "replacement": "[secret]"}
    assert RedactionRule.from_dict(rule.to_dict()) == rule
    assert RedactionRule("users.*.token", "[x]").segments == ("users", "*", "token")


@pytest.mark.parametrize("field", ["", "a..b", "1bad", "a-b", "."])
def test_redaction_rule_rejects_bad_paths(field: str) -> None:
    with pytest.raises(ValueError, match="field must"):
        RedactionRule(field, "[x]")


def test_redaction_rule_requires_replacement() -> None:
    with pytest.raises(ValueError, match="replacement must not be empty"):
        RedactionRule("token", "   ")


def test_validation_helpers() -> None:
    assert require_text("  value ", "field") == "value"
    assert require_text("  ", "field", allow_empty=True) == ""
    assert require_identifier(KEY_ID.upper(), "id") == KEY_ID
    assert require_identifier(OTHER_ID, "id") == OTHER_ID
    assert require_positive_int(KEY_BYTES, "size") == 32
    assert require_bool(False, "flag") is False
    with pytest.raises(ValueError, match="field must be a string"):
        require_text(12, "field")
    with pytest.raises(ValueError, match="field must be a boolean"):
        require_bool(1, "field")


def test_hex_and_timestamp_normalization() -> None:
    assert normalize_hex("AABB", "value") == "aabb"
    assert normalize_hex("", "value", allow_empty=True) == ""
    assert normalize_timestamp("2026-01-01T00:00:00+00:00", "when").endswith("+00:00")
    with pytest.raises(ValueError, match="value must be a positive integer"):
        require_positive_int(True, "value")
    with pytest.raises(ValueError, match="value must be even-length hexadecimal"):
        normalize_hex("abc", "value")
