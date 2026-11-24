"""Tests for dependency-free authenticated bundle encryption."""

from __future__ import annotations

import pytest

from redscribe.v3.portability.crypto import (
    ALGORITHM,
    DEFAULT_KDF_ITERATIONS,
    EncryptedBlob,
    decrypt_bytes,
    derive_key,
    encrypt_bytes,
    is_strong_passphrase,
    passphrase_strength,
)
from redscribe.v3.portability.errors import DecryptionError, PortabilityError
from tests.v3_portability.conftest import TEST_PASSPHRASE

SALT = b"0123456789abcdef"
NONCE = b"abcdefghijklmnop"


def test_derive_key_is_deterministic() -> None:
    first = derive_key(TEST_PASSPHRASE, SALT, iterations=1_000)
    second = derive_key(TEST_PASSPHRASE, SALT, iterations=1_000)
    assert first == second
    assert len(first) == 32


def test_derive_key_depends_on_salt_and_passphrase() -> None:
    assert derive_key(TEST_PASSPHRASE, SALT, iterations=1_000) != derive_key(
        TEST_PASSPHRASE, b"fedcba9876543210", iterations=1_000
    )
    assert derive_key(TEST_PASSPHRASE, SALT, iterations=1_000) != derive_key(
        "another-passphrase-42", SALT, iterations=1_000
    )


def test_derive_key_rejects_bad_inputs() -> None:
    with pytest.raises(PortabilityError):
        derive_key("", SALT, iterations=1_000)
    with pytest.raises(PortabilityError):
        derive_key(TEST_PASSPHRASE, b"short", iterations=1_000)
    with pytest.raises(PortabilityError):
        derive_key(TEST_PASSPHRASE, SALT, iterations=5)


def test_encrypt_decrypt_round_trip() -> None:
    plaintext = b"flag{this-is-a-test-secret}"
    blob = encrypt_bytes(
        plaintext,
        TEST_PASSPHRASE,
        iterations=1_000,
        salt=SALT,
        nonce=NONCE,
    )
    assert blob.algorithm == ALGORITHM
    assert blob.iterations == 1_000
    assert decrypt_bytes(blob, TEST_PASSPHRASE) == plaintext


def test_ciphertext_does_not_leak_plaintext() -> None:
    blob = encrypt_bytes(
        b"highly-classified-vault-title",
        TEST_PASSPHRASE,
        iterations=1_000,
        salt=SALT,
        nonce=NONCE,
    )
    assert b"highly" not in blob.ciphertext
    assert repr(blob).find("highly") == -1


def test_wrong_passphrase_is_refused() -> None:
    blob = encrypt_bytes(b"payload", TEST_PASSPHRASE, iterations=1_000)
    with pytest.raises(DecryptionError, match="authentication failed"):
        decrypt_bytes(blob, "Wrong-Passphrase-99")


def test_tampered_ciphertext_is_refused() -> None:
    blob = encrypt_bytes(b"payload", TEST_PASSPHRASE, iterations=1_000)
    altered = EncryptedBlob(
        salt=blob.salt,
        nonce=blob.nonce,
        ciphertext=b"altered-payload-bytes",
        tag=blob.tag,
        iterations=blob.iterations,
        algorithm=blob.algorithm,
        aad=blob.aad,
    )
    with pytest.raises(DecryptionError):
        decrypt_bytes(altered, TEST_PASSPHRASE)


def test_tampered_tag_is_refused() -> None:
    blob = encrypt_bytes(b"payload", TEST_PASSPHRASE, iterations=1_000)
    altered = EncryptedBlob(
        salt=blob.salt,
        nonce=blob.nonce,
        ciphertext=blob.ciphertext,
        tag=b"\x00" * 32,
        iterations=blob.iterations,
        algorithm=blob.algorithm,
        aad=blob.aad,
    )
    with pytest.raises(DecryptionError):
        decrypt_bytes(altered, TEST_PASSPHRASE)


def test_additional_authenticated_data_is_bound() -> None:
    blob = encrypt_bytes(b"payload", TEST_PASSPHRASE, aad="bundle-42", iterations=1_000)
    assert decrypt_bytes(blob, TEST_PASSPHRASE) == b"payload"
    altered = EncryptedBlob(
        salt=blob.salt,
        nonce=blob.nonce,
        ciphertext=blob.ciphertext,
        tag=blob.tag,
        iterations=blob.iterations,
        algorithm=blob.algorithm,
        aad="bundle-43",
    )
    with pytest.raises(DecryptionError):
        decrypt_bytes(altered, TEST_PASSPHRASE)


def test_blob_serialization_round_trip() -> None:
    blob = encrypt_bytes(b"payload", TEST_PASSPHRASE, aad="ctx", iterations=1_000)
    payload = blob.as_dict()
    assert payload["algorithm"] == ALGORITHM
    restored = EncryptedBlob.from_dict(payload)
    assert restored.as_dict() == payload
    assert decrypt_bytes(restored, TEST_PASSPHRASE) == b"payload"


def test_malformed_blob_is_refused() -> None:
    with pytest.raises(DecryptionError):
        EncryptedBlob.from_dict({"algorithm": ALGORITHM})
    blob = encrypt_bytes(b"payload", TEST_PASSPHRASE, iterations=1_000)
    with pytest.raises(PortabilityError):
        EncryptedBlob(
            salt=blob.salt,
            nonce=blob.nonce,
            ciphertext=blob.ciphertext,
            tag=blob.tag,
            iterations=blob.iterations,
            algorithm="unknown-algorithm",
        )


def test_default_iterations_are_documented() -> None:
    assert DEFAULT_KDF_ITERATIONS >= 1_000
    assert len(NONCE) == 16
    assert len(SALT) == 16


def test_passphrase_strength_scoring() -> None:
    assert passphrase_strength("") == 0
    assert passphrase_strength("aaaaaaaaaaaa") == 1
    assert passphrase_strength("Abcdefgh1234") >= 2
    assert passphrase_strength("Str0ng!Passphrase#2026") >= 3


def test_strong_passphrase_policy() -> None:
    assert is_strong_passphrase("Str0ng!Passphrase", minimum_length=8)
    assert not is_strong_passphrase("short", minimum_length=8)
    assert not is_strong_passphrase("alllowercaseletters", minimum_length=8)
