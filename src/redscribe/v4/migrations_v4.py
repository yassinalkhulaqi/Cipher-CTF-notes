"""Append-only schema v6 migration chain for the v4 program.

Migrations are declarative records, not executable SQL strings assembled from
user input. Each migration carries a checksum so a partially applied chain can
be detected and refused. Downgrades are explicitly rejected.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 6
MIN_COMPATIBLE_VERSION = 5

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class MigrationError(Exception):
    """Raised when a migration chain is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class Column:
    """A column declaration in a migration."""

    name: str
    kind: str
    nullable: bool = True
    default: Any = None

    def __post_init__(self) -> None:
        if not IDENTIFIER_PATTERN.match(self.name):
            raise MigrationError(f"invalid column name: {self.name}")
        if self.kind not in {"TEXT", "INTEGER", "REAL", "BLOB"}:
            raise MigrationError(f"unsupported column kind: {self.kind}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "nullable": self.nullable,
            "default": self.default,
        }


@dataclass(frozen=True, slots=True)
class Migration:
    """A single forward migration step."""

    version: int
    name: str
    table: str
    columns: tuple[Column, ...] = field(default_factory=tuple)
    indexes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise MigrationError("version must be >= 1")
        if not IDENTIFIER_PATTERN.match(self.table):
            raise MigrationError(f"invalid table name: {self.table}")
        for index in self.indexes:
            if not IDENTIFIER_PATTERN.match(index):
                raise MigrationError(f"invalid index name: {index}")

    @property
    def checksum(self) -> str:
        payload = [self.version, self.name, self.table]
        payload.extend(col.to_dict() for col in self.columns)
        payload.extend(self.indexes)
        raw = repr(payload).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "table": self.table,
            "columns": [col.to_dict() for col in self.columns],
            "indexes": list(self.indexes),
            "checksum": self.checksum,
        }


def _text(name: str, *, nullable: bool = True) -> Column:
    return Column(name, "TEXT", nullable=nullable)


def _integer(name: str, *, nullable: bool = True) -> Column:
    return Column(name, "INTEGER", nullable=nullable)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=6,
        name="v4_entities",
        table="v4_entities",
        columns=(
            _text("id", nullable=False),
            _text("kind", nullable=False),
            _text("title"),
            _integer("created_at"),
        ),
        indexes=("v4_entities_kind", "v4_entities_created"),
    ),
    Migration(
        version=6,
        name="v4_inbox_items",
        table="v4_inbox_items",
        columns=(
            _text("id", nullable=False),
            _text("raw", nullable=False),
            _text("source"),
            _text("status", nullable=False),
        ),
        indexes=("v4_inbox_status",),
    ),
    Migration(
        version=6,
        name="v4_findings_v4",
        table="v4_findings_v4",
        columns=(
            _text("id", nullable=False),
            _text("cvss_vector"),
            _text("severity"),
            _text("lifecycle_state"),
        ),
        indexes=("v4_findings_severity",),
    ),
    Migration(
        version=6,
        name="v4_evidence_inspections",
        table="v4_evidence_inspections",
        columns=(
            _text("id", nullable=False),
            _text("evidence_id", nullable=False),
            _text("sha256"),
            _integer("size"),
        ),
        indexes=("v4_evidence_sha256",),
    ),
    Migration(
        version=6,
        name="v4_queries",
        table="v4_queries",
        columns=(
            _text("id", nullable=False),
            _text("name", nullable=False),
            _text("expression", nullable=False),
        ),
        indexes=("v4_queries_name",),
    ),
    Migration(
        version=6,
        name="v4_runs",
        table="v4_runs",
        columns=(
            _text("id", nullable=False),
            _text("playbook_id", nullable=False),
            _text("status", nullable=False),
            _integer("started_at"),
        ),
        indexes=("v4_runs_status",),
    ),
    Migration(
        version=6,
        name="v4_report_layouts",
        table="v4_report_layouts",
        columns=(
            _text("id", nullable=False),
            _text("theme"),
            _text("page_size"),
            _integer("version"),
        ),
        indexes=("v4_report_theme",),
    ),
    Migration(
        version=6,
        name="v4_graph_filters",
        table="v4_graph_filters",
        columns=(
            _text("id", nullable=False),
            _text("name", nullable=False),
            _text("expression"),
        ),
        indexes=("v4_graph_filters_name",),
    ),
    Migration(
        version=6,
        name="v4_key_metadata",
        table="v4_key_metadata",
        columns=(
            _text("id", nullable=False),
            _integer("version"),
            _integer("rotated_at"),
        ),
        indexes=("v4_key_version",),
    ),
    Migration(
        version=6,
        name="v4_preferences",
        table="v4_preferences",
        columns=(
            _text("id", nullable=False),
            _text("locale"),
            _text("theme"),
            _text("motion"),
        ),
        indexes=("v4_preferences_locale",),
    ),
)


class MigrationChain:
    """An ordered, checksummed collection of migrations."""

    def __init__(self, migrations: tuple[Migration, ...] = MIGRATIONS) -> None:
        if not migrations:
            raise MigrationError("empty migration chain")
        versions = {migration.version for migration in migrations}
        if versions != {SCHEMA_VERSION}:
            raise MigrationError(f"unexpected versions in chain: {sorted(versions)}")
        names = [migration.name for migration in migrations]
        if len(set(names)) != len(names):
            raise MigrationError("duplicate migration names")
        self.migrations = migrations

    @property
    def digest(self) -> str:
        raw = "".join(migration.checksum for migration in self.migrations).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def apply_from(self, current_version: int) -> list[Migration]:
        if current_version > SCHEMA_VERSION:
            raise MigrationError("vault schema is newer than the application")
        if current_version < MIN_COMPATIBLE_VERSION:
            raise MigrationError("vault schema is too old for v4")
        if current_version == SCHEMA_VERSION:
            return []
        return list(self.migrations)

    def refuse_downgrade(self, target_version: int) -> None:
        if target_version < SCHEMA_VERSION:
            raise MigrationError("schema downgrades are not supported")

    def table_names(self) -> list[str]:
        return sorted(migration.table for migration in self.migrations)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "chain_digest": self.digest,
            "migrations": [migration.to_dict() for migration in self.migrations],
        }


DEFAULT_CHAIN = MigrationChain()
