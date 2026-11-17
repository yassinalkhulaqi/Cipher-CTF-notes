"""Ordered, immutable SQLite schema migrations for the vault."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable schema revision."""

    version: int
    name: str
    sql: str


class UnknownMigrationError(KeyError, ValueError):
    """Raised when a requested migration version does not exist."""


_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('folder', 'note')),
    content TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    difficulty TEXT NOT NULL DEFAULT '',
    flag TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_nodes_parent
    ON nodes(parent_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_nodes_deleted ON nodes(deleted_at);
CREATE INDEX IF NOT EXISTS idx_nodes_updated ON nodes(updated_at DESC);

CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    command TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
"""

_MIGRATION_2 = """
CREATE INDEX IF NOT EXISTS idx_nodes_kind
    ON nodes(kind, deleted_at, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_target
    ON nodes(target)
    WHERE deleted_at IS NULL AND target <> '';
CREATE INDEX IF NOT EXISTS idx_nodes_pinned
    ON nodes(updated_at DESC)
    WHERE deleted_at IS NULL AND pinned = 1;
CREATE INDEX IF NOT EXISTS idx_snippets_title
    ON snippets(title COLLATE NOCASE);
"""

_MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS nodes_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT '',
    flag TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_history_node
    ON nodes_history(node_id, id DESC);
"""

_MIGRATION_4 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    request_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_events_created_at
    ON entity_events(created_at);
CREATE INDEX IF NOT EXISTS idx_entity_events_entity
    ON entity_events(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    method TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status INTEGER NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_expires_at
    ON idempotency_keys(expires_at);

CREATE TABLE IF NOT EXISTS request_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms REAL NOT NULL DEFAULT 0,
    client TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_request_audit_created_at
    ON request_audit(created_at);
"""

MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial schema", _MIGRATION_1),
    Migration(2, "query indexes", _MIGRATION_2),
    Migration(3, "node history", _MIGRATION_3),
    Migration(4, "platform storage", _MIGRATION_4),
)

SCHEMA_VERSION = MIGRATIONS[-1].version


def migration_for(version: int) -> Migration:
    """Return the migration with ``version`` or raise if it is unknown."""
    for migration in MIGRATIONS:
        if migration.version == version:
            return migration
    raise UnknownMigrationError(f"Unknown SQLite migration version: {version}")


def migrations_through(target: int) -> list[Migration]:
    """Return every migration at or below ``target`` in application order."""
    return [migration for migration in MIGRATIONS if migration.version <= target]


def validate_migration_chain() -> None:
    """Validate that the built-in migration chain is complete and ordered."""
    if not MIGRATIONS:
        raise ValueError("Migration chain must contain at least one migration")
    seen: set[int] = set()
    seen_names: set[str] = set()
    for expected, migration in enumerate(MIGRATIONS, start=1):
        if migration.version != expected:
            raise ValueError(
                "Migration versions must be contiguous starting at 1; "
                f"expected {expected}, found {migration.version}"
            )
        if migration.version in seen:
            raise ValueError(f"Duplicate migration version: {migration.version}")
        if not migration.name.strip():
            raise ValueError(f"Migration {migration.version} has an empty name")
        if migration.name in seen_names:
            raise ValueError(f"Duplicate migration name: {migration.name}")
        if not migration.sql.strip():
            raise ValueError(f"Migration {migration.version} has empty SQL")
        seen.add(migration.version)
        seen_names.add(migration.name)
