"""Tests for stdlib-only vault encryption."""

from __future__ import annotations

import base64
import json

import pytest

from redscribe.v3.vault_security.crypto import (
    FORMAT_VERSION,
    MAGIC,
    MIN_ITERATIONS,
    RECOMMENDED_ITERATIONS,
    VaultIntegrityError,
    VaultKdfParams,
    VaultSeal,
    decrypt_vault,
    derive_vault_key,
    encrypt_vault,
    key_verifier,
    seal_json,
    unseal_json,
    verify_vault_passphrase,
)

FAST = VaultKdfParams(iterations=MIN_ITERATIONS)
PASSPHRASE = "correct horse battery staple 2026!"


def test_round_trip_bytes() -> None:
    plaintext = b"vault payload with unicode \xe2\x9c\x93 and bytes \x00\xff"
    seal = encrypt_vault(plaintext, PASSPHRASE, params=FAST)
    assert seal.version == FORMAT_VERSION
    assert seal.ciphertext_bytes == len(plaintext)
    assert decrypt_vault(seal, PASSPHRASE) == plaintext
    assert seal.to_dict()["magic"] == MAGIC
    assert seal.to_json() == VaultSeal.from_json(seal.to_json()).to_json()


def test_ciphertext_does_not_contain_plaintext() -> None:
    secret = "supersecret-value-12345"
    seal = encrypt_vault(secret.encode("utf-8"), PASSPHRASE, params=FAST)
    assert secret not in seal.to_json()
    assert secret not in json.dumps(seal.to_dict())


def test_wrong_key_refusal() -> None:
    seal = encrypt_vault(b"sensitive", PASSPHRASE, params=FAST)
    with pytest.raises(VaultIntegrityError, match="authentication tag mismatch"):
        decrypt_vault(seal, "an entirely different passphrase")
    assert verify_vault_passphrase(seal, PASSPHRASE) is True
    assert verify_vault_passphrase(seal, "an entirely different passphrase") is False


def test_tampering_is_detected() -> None:
    seal = encrypt_vault(b"important data", PASSPHRASE, params=FAST)
    payload = seal.to_dict()
    raw = bytearray(base64.urlsafe_b64decode(payload["ciphertext"]))
    raw[0] ^= 0xFF
    payload["ciphertext"] = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(VaultIntegrityError, match="authentication tag mismatch"):
        decrypt_vault(payload, PASSPHRASE)


def test_vault_id_binding() -> None:
    seal = encrypt_vault(b"data", PASSPHRASE, params=FAST, vault_id="case-alpha")
    assert decrypt_vault(seal, PASSPHRASE, vault_id="case-alpha") == b"data"
    with pytest.raises(VaultIntegrityError, match="different vault"):
        decrypt_vault(seal, PASSPHRASE, vault_id="case-beta")
    assert verify_vault_passphrase(seal, PASSPHRASE, vault_id="case-beta") is False


def test_associated_data_binding() -> None:
    seal = encrypt_vault(b"data", PASSPHRASE, params=FAST, associated_data=b"meta")
    assert decrypt_vault(seal, PASSPHRASE, associated_data=b"meta") == b"data"
    with pytest.raises(VaultIntegrityError, match="authentication tag mismatch"):
        decrypt_vault(seal, PASSPHRASE, associated_data=b"other")


def test_json_helpers_and_validation() -> None:
    original = {"notes": [{"id": "note-1", "title": "alpha"}], "count": 2}
    seal = seal_json(original, PASSPHRASE, params=FAST)
    assert unseal_json(seal.to_json(), PASSPHRASE) == original
    with pytest.raises(VaultIntegrityError, match="Unsupported vault seal format"):
        VaultSeal.from_dict({"version": 1})
    with pytest.raises(VaultIntegrityError, match="missing salt"):
        VaultSeal.from_dict({"magic": MAGIC, "version": 1, "kdf": FAST.as_dict()})


def test_empty_plaintext_and_large_plaintext() -> None:
    empty = encrypt_vault(b"", PASSPHRASE, params=FAST)
    assert decrypt_vault(empty, PASSPHRASE) == b""
    large = bytes(range(256)) * 40
    assert decrypt_vault(encrypt_vault(large, PASSPHRASE, params=FAST), PASSPHRASE) == large


def test_invalid_inputs_and_parameters() -> None:
    with pytest.raises(ValueError, match="passphrase"):
        derive_vault_key("", b"0" * 16, params=FAST)
    with pytest.raises(TypeError, match="salt"):
        derive_vault_key(PASSPHRASE, "not-bytes", params=FAST)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="iterations"):
        VaultKdfParams(iterations=MIN_ITERATIONS - 1)
    with pytest.raises(ValueError, match="length"):
        VaultKdfParams(length=8)
    with pytest.raises(TypeError, match="plaintext"):
        encrypt_vault("text", PASSPHRASE, params=FAST)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="seal"):
        decrypt_vault(123, PASSPHRASE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="vault_id"):
        encrypt_vault(b"x", PASSPHRASE, params=FAST, vault_id="bad\x00id")


def test_key_verifier_is_non_reversible_and_stable() -> None:
    key = derive_vault_key(PASSPHRASE, b"0" * 16, params=FAST)
    verifier = key_verifier(key)
    assert verifier == key_verifier(key)
    assert PASSPHRASE not in verifier
    assert key.hex() not in verifier
    assert verifier != key_verifier(key[::-1])


def test_recommended_iterations_threshold() -> None:
    assert RECOMMENDED_ITERATIONS >= MIN_ITERATIONS
    assert VaultKdfParams().strong is True
    assert FAST.strong is False
    assert VaultKdfParams.from_dict(FAST.as_dict()) == FAST
