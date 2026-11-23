"""Schema migration contracts for RedScribe V3."""

from __future__ import annotations

from redscribe.v3.migrations.registry import (
    AppliedMigration,
    MigrationChain,
    MigrationError,
    chain,
)
from redscribe.v3.migrations.v5 import (
    INDEXES,
    MIGRATION_STEPS,
    SCHEMA_VERSION,
    MigrationStep,
    migration_checksum,
)

__all__ = [
    "INDEXES",
    "MIGRATION_STEPS",
    "SCHEMA_VERSION",
    "AppliedMigration",
    "MigrationChain",
    "MigrationError",
    "MigrationStep",
    "chain",
    "migration_checksum",
]
