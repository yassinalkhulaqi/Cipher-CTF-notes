"""Append-only schema v5 migration steps."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

SCHEMA_VERSION: Final[int] = 5
PREVIOUS_SCHEMA_VERSION: Final[int] = 4

TABLES: tuple[str, ...] = (
    "v3_entities",
    "v3_entity_links",
    "v3_activity_events",
    "v3_findings",
    "v3_finding_lifecycle",
    "v3_remediation",
    "v3_evidence_records",
    "v3_evidence_chunks",
    "v3_custody_events",
    "v3_graph_snapshots",
    "v3_search_saved",
    "v3_run_records",
    "v3_report_layouts",
    "v3_sync_state",
    "v3_key_metadata",
    "v3_extension_manifests",
)

INDEXES: tuple[str, ...] = (
    "idx_v3_entities_kind",
    "idx_v3_entities_status",
    "idx_v3_links_source",
    "idx_v3_links_target",
    "idx_v3_activity_sequence",
    "idx_v3_activity_subject",
    "idx_v3_findings_severity",
    "idx_v3_evidence_hash",
    "idx_v3_runs_started",
)


@dataclass(frozen=True, slots=True)
class MigrationStep:
    """One idempotent migration step."""

    name: str
    sql: str
    requires: tuple[str, ...] = ()

    @property
    def checksum(self) -> str:
        """Stable checksum of the migration SQL."""
        return hashlib.blake2b(self.sql.encode("utf-8"), digest_size=8).hexdigest()


def _create(table: str, columns: str) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement."""
    return f"CREATE TABLE IF NOT EXISTS {table} ({columns});"


def _index(name: str, table: str, columns: str) -> str:
    """Build a CREATE INDEX IF NOT EXISTS statement."""
    return f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns});"


TABLE_STEPS: tuple[MigrationStep, ...] = (
    MigrationStep(
        "create_entities",
        _create(
            "v3_entities",
            "ref TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, "
            "status TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]', "
            "summary TEXT NOT NULL DEFAULT '', "
            "owner TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, "
            "updated_at REAL NOT NULL, "
            "version INTEGER NOT NULL DEFAULT 1, metadata TEXT NOT NULL DEFAULT '{}'",
        ),
    ),
    MigrationStep(
        "create_entity_links",
        _create(
            "v3_entity_links",
            "source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL, "
            "label TEXT NOT NULL DEFAULT '', weight REAL NOT NULL DEFAULT 1.0, "
            "metadata TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (source, target, kind)",
        ),
    ),
    MigrationStep(
        "create_activity_events",
        _create(
            "v3_activity_events",
            "sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
            "subject TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT 'local', "
            "severity TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', "
            "correlation_id TEXT NOT NULL DEFAULT '', timestamp REAL NOT NULL, "
            "request_id TEXT NOT NULL DEFAULT ''",
        ),
    ),
    MigrationStep(
        "create_findings",
        _create(
            "v3_findings",
            "ref TEXT PRIMARY KEY, title TEXT NOT NULL, severity TEXT NOT NULL, "
            "cvss_score REAL NOT NULL DEFAULT 0.0, cvss_vector TEXT NOT NULL DEFAULT '', "
            "status TEXT NOT NULL, target_ref TEXT NOT NULL DEFAULT '', "
            "remediation TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}'",
        ),
    ),
    MigrationStep(
        "create_finding_lifecycle",
        _create(
            "v3_finding_lifecycle",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, finding_ref TEXT NOT NULL, "
            "from_status TEXT NOT NULL, to_status TEXT NOT NULL, actor TEXT NOT NULL, "
            "note TEXT NOT NULL DEFAULT '', timestamp REAL NOT NULL",
        ),
    ),
    MigrationStep(
        "create_remediation",
        _create(
            "v3_remediation",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, finding_ref TEXT NOT NULL, "
            "action TEXT NOT NULL, owner TEXT NOT NULL DEFAULT '', "
            "done INTEGER NOT NULL DEFAULT 0, due_at REAL NOT NULL DEFAULT 0",
        ),
    ),
    MigrationStep(
        "create_evidence_records",
        _create(
            "v3_evidence_records",
            "ref TEXT PRIMARY KEY, path TEXT NOT NULL, mime TEXT NOT NULL DEFAULT '', "
            "size INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '', "
            "blake2b TEXT NOT NULL DEFAULT '', captured_at REAL NOT NULL, "
            "metadata TEXT NOT NULL DEFAULT '{}'",
        ),
    ),
    MigrationStep(
        "create_evidence_chunks",
        _create(
            "v3_evidence_chunks",
            "evidence_ref TEXT NOT NULL, offset INTEGER NOT NULL, data BLOB NOT NULL, "
            "PRIMARY KEY (evidence_ref, offset)",
        ),
    ),
    MigrationStep(
        "create_custody_events",
        _create(
            "v3_custody_events",
            "id INTEGER PRIMARY KEY AUTOINCREMENT, evidence_ref TEXT NOT NULL, "
            "action TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', "
            "timestamp REAL NOT NULL, signature TEXT NOT NULL DEFAULT ''",
        ),
    ),
    MigrationStep(
        "create_graph_snapshots",
        _create(
            "v3_graph_snapshots",
            "id TEXT PRIMARY KEY, label TEXT NOT NULL, payload TEXT NOT NULL, "
            "created_at REAL NOT NULL, node_count INTEGER NOT NULL DEFAULT 0, "
            "edge_count INTEGER NOT NULL DEFAULT 0",
        ),
    ),
    MigrationStep(
        "create_search_saved",
        _create(
            "v3_search_saved",
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, query TEXT NOT NULL, "
            "facets TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, "
            "usage INTEGER NOT NULL DEFAULT 0",
        ),
    ),
    MigrationStep(
        "create_run_records",
        _create(
            "v3_run_records",
            "id TEXT PRIMARY KEY, playbook_ref TEXT NOT NULL, status TEXT NOT NULL, "
            "mode TEXT NOT NULL, started_at REAL NOT NULL, finished_at REAL NOT NULL DEFAULT 0, "
            "trace TEXT NOT NULL DEFAULT '[]'",
        ),
    ),
    MigrationStep(
        "create_report_layouts",
        _create(
            "v3_report_layouts",
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, theme TEXT NOT NULL DEFAULT 'default', "
            "layout TEXT NOT NULL DEFAULT '{}', updated_at REAL NOT NULL",
        ),
    ),
    MigrationStep(
        "create_sync_state",
        _create(
            "v3_sync_state",
            "device_id TEXT PRIMARY KEY, label TEXT NOT NULL, vector TEXT NOT NULL DEFAULT '{}', "
            "last_sync REAL NOT NULL DEFAULT 0",
        ),
    ),
    MigrationStep(
        "create_key_metadata",
        _create(
            "v3_key_metadata",
            "id TEXT PRIMARY KEY, algorithm TEXT NOT NULL, created_at REAL NOT NULL, "
            "rotated_at REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, "
            "fingerprint TEXT NOT NULL DEFAULT ''",
        ),
    ),
    MigrationStep(
        "create_extension_manifests",
        _create(
            "v3_extension_manifests",
            "name TEXT PRIMARY KEY, version TEXT NOT NULL, "
            "capabilities TEXT NOT NULL DEFAULT '[]', "
            "enabled INTEGER NOT NULL DEFAULT 0, checksum TEXT NOT NULL DEFAULT ''",
        ),
    ),
)

INDEX_STEPS: tuple[MigrationStep, ...] = (
    MigrationStep("idx_entities_kind", _index(INDEXES[0], "v3_entities", "kind")),
    MigrationStep("idx_entities_status", _index(INDEXES[1], "v3_entities", "status")),
    MigrationStep("idx_links_source", _index(INDEXES[2], "v3_entity_links", "source")),
    MigrationStep("idx_links_target", _index(INDEXES[3], "v3_entity_links", "target")),
    MigrationStep("idx_activity_sequence", _index(INDEXES[4], "v3_activity_events", "sequence")),
    MigrationStep("idx_activity_subject", _index(INDEXES[5], "v3_activity_events", "subject")),
    MigrationStep("idx_findings_severity", _index(INDEXES[6], "v3_findings", "severity")),
    MigrationStep("idx_evidence_hash", _index(INDEXES[7], "v3_evidence_records", "sha256")),
    MigrationStep("idx_runs_started", _index(INDEXES[8], "v3_run_records", "started_at")),
)

MIGRATION_STEPS: tuple[MigrationStep, ...] = TABLE_STEPS + INDEX_STEPS


def migration_checksum() -> str:
    """Return a checksum over the whole ordered migration chain."""
    payload = "|".join(f"{step.name}:{step.checksum}" for step in MIGRATION_STEPS)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()
