from __future__ import annotations

import re
from pathlib import Path

from redscribe.storage.db import Vault
from redscribe.storage.idempotency import (
    IdempotencyRecord,
    get_record,
    hash_request,
    prune_expired,
    put_record,
)


def test_hash_request_is_stable_and_order_independent() -> None:
    first = hash_request("POST", {"b": 1, "a": {"z": 2, "y": 3}})
    second = hash_request("post", {"a": {"y": 3, "z": 2}, "b": 1})
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert hash_request("POST", {"a": 1}) != hash_request("POST", {"a": 2})
    assert hash_request("GET", {"a": 1}) != hash_request("POST", {"a": 1})


def test_put_and_get_record_round_trip(vault: Vault) -> None:
    record = put_record(
        vault.connection,
        key="key-1",
        method="POST",
        request_hash="hash-1",
        status=201,
        response={"b": 2, "a": 1},
        ttl_seconds=60,
        now="2026-01-01T00:00:00+00:00",
    )
    assert isinstance(record, IdempotencyRecord)
    assert record.key == "key-1"
    assert record.method == "POST"
    assert record.request_hash == "hash-1"
    assert record.status == 201
    assert record.response == {"a": 1, "b": 2}
    assert record.created_at == "2026-01-01T00:00:00+00:00"
    assert record.expires_at == "2026-01-01T00:01:00+00:00"
    assert get_record(vault.connection, "key-1") == record
    assert get_record(vault.connection, "missing") is None

    row = vault.connection.execute(
        "SELECT response FROM idempotency_keys WHERE key = ?", ("key-1",)
    ).fetchone()
    assert row is not None
    assert str(row["response"]) == '{"a":1,"b":2}'


def test_put_record_replaces_existing_key(vault: Vault) -> None:
    first = put_record(
        vault.connection,
        key="same",
        method="POST",
        request_hash="hash-1",
        status=200,
        response={"version": 1},
        ttl_seconds=10,
        now="2026-01-01T00:00:00+00:00",
    )
    replacement = put_record(
        vault.connection,
        key="same",
        method="PUT",
        request_hash="hash-2",
        status=202,
        response={"version": 2},
        ttl_seconds=3600,
        now="2026-01-01T01:00:00+00:00",
    )
    assert replacement != first
    assert get_record(vault.connection, "same") == replacement
    assert replacement.method == "PUT"
    assert replacement.status == 202
    assert replacement.response == {"version": 2}
    assert replacement.expires_at == "2026-01-01T02:00:00+00:00"
    count = vault.connection.execute("SELECT COUNT(*) FROM idempotency_keys").fetchone()
    assert count is not None
    assert int(count[0]) == 1


def test_prune_expired_respects_ttl_boundary(vault: Vault) -> None:
    put_record(
        vault.connection,
        key="short",
        method="POST",
        request_hash="hash-1",
        status=200,
        response={"ok": True},
        ttl_seconds=10,
        now="2026-01-01T00:00:00+00:00",
    )
    put_record(
        vault.connection,
        key="long",
        method="POST",
        request_hash="hash-2",
        status=200,
        response={"ok": True},
        ttl_seconds=3600,
        now="2026-01-01T00:00:00+00:00",
    )

    assert prune_expired(vault.connection, now="2026-01-01T00:00:05+00:00") == 0
    assert get_record(vault.connection, "short") is not None
    assert prune_expired(vault.connection, now="2026-01-01T00:00:10+00:00") == 1
    assert get_record(vault.connection, "short") is None
    assert get_record(vault.connection, "long") is not None


def test_prune_expired_removes_already_expired_records(vault: Vault) -> None:
    put_record(
        vault.connection,
        key="expired",
        method="POST",
        request_hash="hash",
        status=200,
        response={},
        ttl_seconds=-1,
        now="2026-01-01T00:00:00+00:00",
    )
    assert prune_expired(vault.connection, now="2026-01-01T00:00:00+00:00") == 1
    assert get_record(vault.connection, "expired") is None


def test_vault_idempotency_wrappers_persist(tmp_path: Path) -> None:
    path = tmp_path / "idempotency.db"
    request_hash = hash_request("POST", {"title": "Persisted"})
    with Vault(path) as vault:
        record = vault.idempotency_put(
            key="request-1",
            method="POST",
            request_hash=request_hash,
            status=201,
            response={"ok": True, "node_id": 4},
        )
        assert vault.idempotency_get("request-1") == record
        assert vault.idempotency_get("missing") is None

    with Vault(path) as reopened:
        restored = reopened.idempotency_get("request-1")
        assert restored == record
        assert restored is not None
        assert restored.response == {"node_id": 4, "ok": True}
        assert reopened.idempotency_prune(now="2099-01-01T00:00:00+00:00") == 1
        assert reopened.idempotency_get("request-1") is None
