from __future__ import annotations

import pytest

from redscribe.v2.security.encryption import (
    EncryptedPayload,
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    encrypt_text,
)
from redscribe.v2.security.kdf import (
    DerivedKey,
    KdfParams,
    derive_key,
    derive_key_material,
    generate_salt,
    stretch_iterations,
    verify_passphrase,
)


def test_kdf_params_and_salt_generation() -> None:
    params = KdfParams(iterations=120000, salt_bytes=16, length=32)
    assert params.as_dict()["algorithm"] == "pbkdf2_hmac_sha256"
    roundtrip = KdfParams.from_dict(params.as_dict())
    assert roundtrip == params
    salt = generate_salt(16)
    assert isinstance(salt, bytes)
    assert len(salt) == 16
    with pytest.raises(ValueError):
        KdfParams(iterations=1000)
    with pytest.raises(ValueError):
        generate_salt(4)


def test_derive_key_material_and_verify_passphrase() -> None:
    params = KdfParams(iterations=120000, length=32)
    salt = generate_salt(16)
    key_a = derive_key_material("correct horse", salt, params=params)
    key_b = derive_key_material("correct horse", salt, params=params)
    key_c = derive_key_material("battery staple", salt, params=params)
    assert key_a == key_b
    assert key_a != key_c
    assert len(key_a) == 32
    derived = derive_key("correct horse", salt=salt, params=params)
    assert isinstance(derived, DerivedKey)
    assert len(derived.key) == 32
    assert len(derived.salt) == 16
    assert verify_passphrase(
        "correct horse",
        expected_key_b64=derived.key_b64,
        salt_b64=derived.salt_b64,
        params=derived.params,
    )
    assert not verify_passphrase(
        "wrong",
        expected_key_b64=derived.key_b64,
        salt_b64=derived.salt_b64,
        params=derived.params,
    )
    with pytest.raises(ValueError):
        derive_key("", params=params)
    with pytest.raises(TypeError):
        derive_key_material("pass", "not-bytes", params=params)  # type: ignore[arg-type]


def test_stretch_iterations_returns_safe_minimum() -> None:
    iterations = stretch_iterations(target_ms=1)
    assert iterations >= 100_000
    with pytest.raises(ValueError):
        stretch_iterations(target_ms=0)


def test_encrypt_and_decrypt_bytes_roundtrip() -> None:
    params = KdfParams(iterations=120000, length=32)
    plaintext = b"sensitive export payload \x00\xff"
    payload = encrypt_bytes(plaintext, "passphrase", params=params, associated_data=b"ctx")
    assert isinstance(payload, EncryptedPayload)
    assert payload.version == 1
    serialized = payload.to_json()
    decoded = decrypt_bytes(serialized, "passphrase", associated_data=b"ctx")
    assert decoded == plaintext
    from_dict = decrypt_bytes(payload.to_dict(), "passphrase", associated_data=b"ctx")
    assert from_dict == plaintext
    with pytest.raises(ValueError):
        decrypt_bytes(serialized, "wrong-passphrase", associated_data=b"ctx")
    with pytest.raises(ValueError):
        decrypt_bytes(serialized, "passphrase", associated_data=b"other")
    with pytest.raises(ValueError):
        decrypt_bytes(
            {
                "magic": "BAD",
                "version": 1,
                "salt": "",
                "nonce": "",
                "ciphertext": "",
                "tag": "",
                "kdf": params.as_dict(),
            },
            "passphrase",
        )


def test_encrypt_and_decrypt_text_roundtrip_and_validation() -> None:
    params = KdfParams(iterations=120000, length=32)
    payload = encrypt_text("hello 🔐", "secret", params=params, associated_data="meta")
    assert payload["magic"] == "RSENC1"
    assert decrypt_text(payload, "secret", associated_data="meta") == "hello 🔐"
    with pytest.raises(TypeError):
        encrypt_text(123, "secret")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        encrypt_text("x", "")
    with pytest.raises(ValueError):
        decrypt_text("not-json", "secret")
    with pytest.raises(TypeError):
        decrypt_text(123, "secret")  # type: ignore[arg-type]
