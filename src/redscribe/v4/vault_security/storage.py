"""Metadata-only persistence for the v4 security vault.

This module stores key descriptors, KDF parameters, and recovery-code digests.
It has no concept of a passphrase, raw derived key, or plaintext recovery code,
and :meth:`KeyMetadataStore.assert_secret_free` enforces that invariant over a
full snapshot. The adapter is in-memory but exposes row projections and a DDL
schema so a SQLite-backed implementation can be added without changing callers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from redscribe.v4.vault_security.types import (
    SALT_BYTES,
    KeyRecord,
    KeySaltRecord,
    KeyState,
    RecoveryCode,
    normalize_hex,
    require_identifier,
)

FORBIDDEN_KEYS = frozenset(
    {
        "ciphertext",
        "code",
        "credential",
        "key_bytes",
        "key_material",
        "mac",
        "nonce",
        "passphrase",
        "password",
        "plaintext",
        "plaintext_code",
        "raw_key",
        "secret",
        "token",
    }
)

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vault_keys (
        id TEXT PRIMARY KEY,
        version INTEGER NOT NULL UNIQUE,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        rotated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_key_salts (
        key_id TEXT PRIMARY KEY,
        salt_hex TEXT NOT NULL,
        iterations INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vault_recovery_codes (
        id TEXT PRIMARY KEY,
        code_hash TEXT NOT NULL UNIQUE,
        used INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
)


class StorageError(Exception):
    """Raised when a metadata operation is invalid or missing."""


def _validate_key(record: KeyRecord) -> KeyRecord:
    if not isinstance(record, KeyRecord):
        raise StorageError("record must be a KeyRecord")
    return record


def _validate_salt(record: KeySaltRecord) -> KeySaltRecord:
    if not isinstance(record, KeySaltRecord):
        raise StorageError("record must be a KeySaltRecord")
    if len(record.salt) != SALT_BYTES:
        raise StorageError("salt must be exactly 16 bytes")
    return record


def _validate_recovery(record: RecoveryCode) -> RecoveryCode:
    if not isinstance(record, RecoveryCode):
        raise StorageError("record must be a RecoveryCode")
    return record


def _walk(value: object, path: str) -> None:
    """Recursively reject secret-shaped field names and unsupported values."""
    if isinstance(value, Mapping):
        for name, child in value.items():
            key = str(name)
            if key.casefold() in FORBIDDEN_KEYS:
                raise StorageError(f"secret-shaped field at {path}.{key}")
            _walk(child, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _walk(child, f"{path}[{index}]")
        return
    if isinstance(value, (str, int, float, bool)) or value is None:
        return
    raise StorageError(f"unsupported value type at {path}: {type(value).__name__}")


class KeyMetadataStore:
    """An append-oriented, secret-free metadata store.

    All reads return defensive copies of immutable records; callers cannot
    mutate stored state by holding a reference to a returned object.
    """

    def __init__(self) -> None:
        self._keys: dict[str, KeyRecord] = {}
        self._salts: dict[str, KeySaltRecord] = {}
        self._recovery: dict[str, RecoveryCode] = {}
        self._hash_index: dict[str, str] = {}

    # -- key descriptors -------------------------------------------------

    def put_key(self, record: KeyRecord) -> KeyRecord:
        key = _validate_key(record)
        if key.id in self._keys:
            raise StorageError(f"key already stored: {key.id}")
        if key.version in self.version_index():
            raise StorageError(f"version already stored: {key.version}")
        self._keys[key.id] = key
        return key

    def get_key(self, key_id: str) -> KeyRecord:
        identifier = require_identifier(key_id, "key_id")
        record = self._keys.get(identifier)
        if record is None:
            raise StorageError(f"unknown key: {identifier}")
        return record

    def find_key(self, key_id: str) -> KeyRecord | None:
        return self._keys.get(require_identifier(key_id, "key_id"))

    def list_keys(self) -> list[KeyRecord]:
        return sorted(self._keys.values(), key=lambda item: item.version)

    def keys_by_state(self, state: KeyState) -> list[KeyRecord]:
        return [record for record in self.list_keys() if record.state is state]

    def active_key(self) -> KeyRecord | None:
        active = self.keys_by_state(KeyState.ACTIVE)
        return active[-1] if active else None

    def version_index(self) -> dict[int, str]:
        return {record.version: record.id for record in self._keys.values()}

    def next_version(self) -> int:
        versions = self.version_index()
        return max(versions) + 1 if versions else 1

    def replace_key(self, record: KeyRecord) -> KeyRecord:
        key = _validate_key(record)
        if key.id not in self._keys:
            raise StorageError(f"unknown key: {key.id}")
        self._keys[key.id] = key
        return key

    def delete_key(self, key_id: str) -> KeyRecord:
        record = self.get_key(key_id)
        del self._keys[record.id]
        self._salts.pop(record.id, None)
        return record

    # -- KDF parameters (not secrets) -----------------------------------

    def put_salt(self, record: KeySaltRecord) -> KeySaltRecord:
        salt = _validate_salt(record)
        if salt.key_id not in self._keys:
            raise StorageError(f"cannot store salt for unknown key: {salt.key_id}")
        if salt.key_id in self._salts:
            raise StorageError(f"salt already stored: {salt.key_id}")
        self._salts[salt.key_id] = salt
        return salt

    def get_salt(self, key_id: str) -> KeySaltRecord:
        identifier = require_identifier(key_id, "key_id")
        record = self._salts.get(identifier)
        if record is None:
            raise StorageError(f"unknown salt: {identifier}")
        return record

    def find_salt(self, key_id: str) -> KeySaltRecord | None:
        return self._salts.get(require_identifier(key_id, "key_id"))

    def list_salts(self) -> list[KeySaltRecord]:
        return sorted(self._salts.values(), key=lambda item: item.key_id)

    # -- recovery-code digests ------------------------------------------

    def put_recovery(self, record: RecoveryCode) -> RecoveryCode:
        code = _validate_recovery(record)
        if code.id in self._recovery:
            raise StorageError(f"recovery code already stored: {code.id}")
        if code.code_hash in self._hash_index:
            raise StorageError("duplicate recovery digest")
        self._recovery[code.id] = code
        self._hash_index[code.code_hash] = code.id
        return code

    def get_recovery(self, code_id: str) -> RecoveryCode:
        identifier = require_identifier(code_id, "code_id")
        record = self._recovery.get(identifier)
        if record is None:
            raise StorageError(f"unknown recovery code: {identifier}")
        return record

    def find_recovery_by_hash(self, code_hash: str) -> RecoveryCode | None:
        digest = normalize_hex(code_hash, "code_hash", exact_bytes=32)
        identifier = self._hash_index.get(digest)
        return None if identifier is None else self._recovery.get(identifier)

    def list_recovery(self) -> list[RecoveryCode]:
        return sorted(self._recovery.values(), key=lambda item: item.created_at)

    def mark_recovery_used(self, code_id: str) -> RecoveryCode:
        record = self.get_recovery(code_id)
        updated = replace(record, used=True)
        self._recovery[updated.id] = updated
        return updated

    def delete_recovery(self, code_id: str) -> RecoveryCode:
        record = self.get_recovery(code_id)
        del self._recovery[record.id]
        self._hash_index.pop(record.code_hash, None)
        return record

    def remaining_recovery(self) -> list[RecoveryCode]:
        return [record for record in self.list_recovery() if not record.used]

    def clear_recovery(self) -> int:
        count = len(self._recovery)
        self._recovery.clear()
        self._hash_index.clear()
        return count

    # -- projections and invariants -------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return every persisted value as JSON-safe metadata."""
        return {
            "keys": [record.to_dict() for record in self.list_keys()],
            "salts": [record.to_dict() for record in self.list_salts()],
            "recovery": [record.to_dict() for record in self.list_recovery()],
        }

    def assert_secret_free(self) -> None:
        """Fail if any persisted field looks like raw secret material."""
        _walk(self.snapshot(), "snapshot")

    def to_rows(self) -> dict[str, tuple[tuple[Any, ...], ...]]:
        """Project metadata into tuples matching :data:`SCHEMA`."""
        keys = tuple(
            (
                record.id,
                record.version,
                record.state.value,
                record.created_at,
                record.rotated_at,
            )
            for record in self.list_keys()
        )
        salts = tuple(
            (record.key_id, record.salt_hex, record.iterations, record.created_at)
            for record in self.list_salts()
        )
        recovery = tuple(
            (record.id, record.code_hash, int(record.used), record.created_at)
            for record in self.list_recovery()
        )
        return {"vault_keys": keys, "vault_key_salts": salts, "vault_recovery_codes": recovery}

    def clear(self) -> None:
        self._keys.clear()
        self._salts.clear()
        self.clear_recovery()

    def __len__(self) -> int:
        return len(self._keys) + len(self._salts) + len(self._recovery)


__all__ = [
    "FORBIDDEN_KEYS",
    "SCHEMA",
    "KeyMetadataStore",
    "StorageError",
]
