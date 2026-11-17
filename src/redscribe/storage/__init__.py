"""Persistent storage for RedScribe.

The storage layer owns the single-file SQLite vault, schema migrations, FTS5
indexing, settings persistence, integrity diagnostics, and retention helpers.
It depends on the domain layer only.
"""

from redscribe.storage.db import Vault
from redscribe.storage.integrity import (
    ISSUE_CODES,
    IntegrityIssue,
    IntegrityReport,
)
from redscribe.storage.retention import CheckpointResult, PruneResult

__all__ = [
    "ISSUE_CODES",
    "CheckpointResult",
    "IntegrityIssue",
    "IntegrityReport",
    "PruneResult",
    "Vault",
]
