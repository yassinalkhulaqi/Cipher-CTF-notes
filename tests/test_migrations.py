from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from redscribe.storage import migrations as migrations_module
from redscribe.storage.db import _MIGRATIONS, SCHEMA_VERSION, Vault
from redscribe.storage.migrations import (
    MIGRATIONS,
    Migration,
    migration_for,
    migrations_through,
    validate_migration_chain,
)

_EXPECTED_TABLES = {
    "entity_events",
    "idempotency_keys",
    "request_audit",
    "schema_migrations",
}

_EXPECTED_INDEXES = {
    "idx_entity_events_created_at",
    "idx_entity_events_entity",
    "idx_idempotency_keys_expires_at",
    "idx_request_audit_created_at",
}


def _legacy_vault(path: Path, version: int) -> None:
    connection = sqlite3.connect(str(path))
    try:
        for migration in migrations_through(version):
            connection.executescript(migration.sql)
        connection.execute(f"PRAGMA user_version = {version}")
        connection.commit()
    finally:
        connection.close()


def _migration_rows(vault: Vault) -> list[sqlite3.Row]:
    return vault.connection.execute(
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()


def test_schema_version_tracks_latest_migration() -> None:
    assert SCHEMA_VERSION == 4
    assert MIGRATIONS[-1].version == SCHEMA_VERSION
    assert sorted(_MIGRATIONS) == [1, 2, 3, 4]
    assert _MIGRATIONS[4] == migration_for(4).sql


def test_empty_vault_migrates_to_latest(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    with Vault(path) as vault:
        assert vault.schema_version == SCHEMA_VERSION
        tables = {
            str(row["name"])
            for row in vault.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            str(row["name"])
            for row in vault.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert tables >= _EXPECTED_TABLES
        assert indexes >= _EXPECTED_INDEXES
        rows = _migration_rows(vault)
        assert [int(row["version"]) for row in rows] == [1, 2, 3, 4]
        assert [str(row["name"]) for row in rows] == [m.name for m in MIGRATIONS]
        assert all(str(row["applied_at"]) for row in rows)
        assert vault.create_node("Fresh").title == "Fresh"

    with Vault(path) as reopened:
        assert len(_migration_rows(reopened)) == 4


@pytest.mark.parametrize("legacy_version", [1, 2, 3])
def test_legacy_vault_upgrades_to_latest(tmp_path: Path, legacy_version: int) -> None:
    path = tmp_path / f"legacy-v{legacy_version}.db"
    _legacy_vault(path, legacy_version)

    with Vault(path) as vault:
        assert vault.schema_version == SCHEMA_VERSION
        assert vault.create_node("Migrated").title == "Migrated"
        tables = {
            str(row["name"])
            for row in vault.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables >= _EXPECTED_TABLES
        rows = _migration_rows(vault)
        assert [int(row["version"]) for row in rows] == [1, 2, 3, 4]
        assert [str(row["name"]) for row in rows] == [m.name for m in MIGRATIONS]


def test_newer_vault_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    with Vault(path) as vault:
        vault.connection.execute("PRAGMA user_version = 999")
        vault.connection.commit()

    with pytest.raises(RuntimeError, match="newer than this RedScribe build"):
        Vault(path)


def test_migration_lookups() -> None:
    assert migration_for(1).version == 1
    assert migration_for(4).version == 4
    assert migrations_through(0) == []
    assert [migration.version for migration in migrations_through(2)] == [1, 2]
    assert [migration.version for migration in migrations_through(99)] == [1, 2, 3, 4]
    with pytest.raises(KeyError):
        migration_for(0)
    with pytest.raises(ValueError):
        migration_for(99)


def test_migration_dataclass_is_frozen() -> None:
    migration = migration_for(1)
    with pytest.raises(FrozenInstanceError):
        migration.version = 2


def test_validate_migration_chain_accepts_builtin_chain() -> None:
    assert validate_migration_chain() is None


def test_validate_migration_chain_rejects_empty_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations_module, "MIGRATIONS", ())
    with pytest.raises(ValueError, match="at least one"):
        migrations_module.validate_migration_chain()


def test_validate_migration_chain_rejects_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = (
        Migration(1, "first", "SELECT 1;"),
        Migration(3, "third", "SELECT 1;"),
    )
    monkeypatch.setattr(migrations_module, "MIGRATIONS", bad)
    with pytest.raises(ValueError, match="contiguous"):
        migrations_module.validate_migration_chain()


def test_validate_migration_chain_rejects_duplicate_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = (
        Migration(1, "same", "SELECT 1;"),
        Migration(2, "same", "SELECT 1;"),
    )
    monkeypatch.setattr(migrations_module, "MIGRATIONS", bad)
    with pytest.raises(ValueError, match="Duplicate migration name"):
        migrations_module.validate_migration_chain()


def test_validate_migration_chain_rejects_empty_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = (Migration(1, "first", "   "),)
    monkeypatch.setattr(migrations_module, "MIGRATIONS", bad)
    with pytest.raises(ValueError, match="empty SQL"):
        migrations_module.validate_migration_chain()


def test_v4_table_columns(vault: Vault) -> None:
    expected = {
        "entity_events": [
            "id",
            "kind",
            "entity_type",
            "entity_id",
            "action",
            "payload",
            "request_id",
            "created_at",
        ],
        "idempotency_keys": [
            "key",
            "method",
            "request_hash",
            "status",
            "response",
            "created_at",
            "expires_at",
        ],
        "request_audit": [
            "id",
            "request_id",
            "method",
            "path",
            "outcome",
            "duration_ms",
            "client",
            "created_at",
        ],
        "schema_migrations": ["version", "name", "applied_at"],
    }
    for table, columns in expected.items():
        rows = vault.connection.execute(f"PRAGMA table_info({table})").fetchall()
        assert [str(row["name"]) for row in rows] == columns
