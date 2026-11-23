"""Tests for the append-only v5 migration chain."""

from __future__ import annotations

import sqlite3

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.migrations.registry import MigrationChain, MigrationError
from redscribe.v3.migrations.v5 import (
    INDEXES,
    MIGRATION_STEPS,
    PREVIOUS_SCHEMA_VERSION,
    SCHEMA_VERSION,
    migration_checksum,
)


def test_migration_chain_metadata() -> None:
    assert SCHEMA_VERSION == 5
    assert PREVIOUS_SCHEMA_VERSION == 4
    assert len(MIGRATION_STEPS) == 25
    assert len(INDEXES) == 9
    assert len({step.name for step in MIGRATION_STEPS}) == len(MIGRATION_STEPS)


def test_migration_chain_validation() -> None:
    chain = MigrationChain()
    assert chain.validate() == ()
    assert len(chain.names()) == len(MIGRATION_STEPS)
    assert len(chain.steps()) == len(MIGRATION_STEPS)
    assert len(migration_checksum()) == 32


def test_migration_chain_rejects_bad_steps() -> None:
    bad = MigrationChain((*MIGRATION_STEPS, MIGRATION_STEPS[0]))
    assert "duplicate migration" in bad.validate()[0]
    with pytest.raises(MigrationError):
        bad.require_valid()


def test_upgrade_plan_and_downgrade_refusal() -> None:
    chain = MigrationChain()
    assert chain.can_upgrade_from(4) is True
    assert chain.can_upgrade_from(5) is False
    assert chain.plan(5) == ()
    plan = chain.plan(4, clock=FixedClock(start=123.0))
    assert len(plan) == len(MIGRATION_STEPS)
    assert plan[0].applied_at == 123.0
    assert all(item.version == 5 for item in plan)
    with pytest.raises(MigrationError):
        chain.plan(3)
    with pytest.raises(MigrationError):
        chain.refuse_downgrade(6)
    assert chain.refuse_downgrade(5) is None


def test_migration_manifest() -> None:
    manifest = MigrationChain().manifest()
    assert manifest["from"] == 4
    assert manifest["to"] == 5
    assert len(manifest["steps"]) == len(MIGRATION_STEPS)


def test_migration_sql_applies_to_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        for step in MIGRATION_STEPS:
            connection.execute(step.sql)
        connection.commit()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "v3_entities" in tables
        assert "v3_findings" in tables
        assert "v3_extension_manifests" in tables
        connection.execute(
            "INSERT INTO v3_entities (ref, kind, title, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("note:1", "note", "Test", "draft", 1.0, 1.0),
        )
        row = connection.execute(
            "SELECT title FROM v3_entities WHERE ref = ?", ("note:1",)
        ).fetchone()
        assert row is not None
        assert row[0] == "Test"
        for step in MIGRATION_STEPS:
            connection.execute(step.sql)
    finally:
        connection.close()
