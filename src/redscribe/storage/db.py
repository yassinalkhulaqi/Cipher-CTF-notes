"""SQLite-backed vault storage for notes, folders, settings, and snippets."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar, cast

from redscribe.domain.flags import find_flags
from redscribe.domain.models import (
    DIFFICULTIES,
    KINDS,
    STATUSES,
    FlagHit,
    Node,
    SearchHit,
    Snippet,
    TagCount,
    VaultStats,
)
from redscribe.domain.utils import collapse_whitespace, slugify, truncate, utc_now
from redscribe.storage import events as storage_events
from redscribe.storage import idempotency as storage_idempotency
from redscribe.storage.integrity import (
    FTS_TRIGGERS,
    IndexDrift,
    IndexRepairResult,
    IntegrityReport,
    contains_control_characters,
    index_drift,
    normalize_tags,
    scan_integrity,
)
from redscribe.storage.migrations import (
    MIGRATIONS,
    SCHEMA_VERSION,
    migrations_through,
    validate_migration_chain,
)
from redscribe.storage.retention import (
    CheckpointResult,
    PruneResult,
    rotate_auto_backups,
    validate_checkpoint_mode,
)

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

_MIGRATIONS: dict[int, str] = {migration.version: migration.sql for migration in MIGRATIONS}

_FTS_TRIGGERS = FTS_TRIGGERS

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    title,
    content,
    tags,
    content='nodes',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS nodes_fts_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE OF title, content, tags ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
    INSERT INTO nodes_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;
"""

_ALLOWED_UPDATE_FIELDS = {
    "title",
    "content",
    "tags",
    "target",
    "status",
    "difficulty",
    "flag",
    "pinned",
}


class Vault:
    """A local SQLite vault.

    All methods are synchronous and intended to be called from one thread.
    Use :meth:`backup_to` for portable snapshots.
    """

    def __init__(self, path: str | Path, *, enable_fts: bool = True) -> None:
        raw_path = str(path)
        self._memory = raw_path == ":memory:"
        self.path: Path | None = None if self._memory else Path(path).expanduser()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            ":memory:" if self._memory else str(self.path),
            timeout=15,
        )
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._stats_cache: tuple[int, VaultStats] | None = None
        self._tag_cache: tuple[int, list[TagCount]] | None = None
        self._flag_cache: dict[int, tuple[int, list[FlagHit]]] = {}
        self._settings_changes = 0
        self._configure()
        self._init_schema()
        self.fts_enabled = False
        if enable_fts:
            self._init_fts()

    @property
    def content_revision(self) -> int:
        return self._connection.total_changes - self._settings_changes

    def __enter__(self) -> Vault:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the connection for read-only integrations and tests."""
        return self._connection

    @property
    def display_path(self) -> str:
        return str(self.path) if self.path is not None else ":memory:"

    @property
    def schema_version(self) -> int:
        """Return the persisted schema revision."""
        return self._read_user_version()

    def _configure(self) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        try:
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.DatabaseError:
            LOGGER.debug("WAL mode unavailable for %s", self.display_path)

    def _read_user_version(self) -> int:
        row = self._connection.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row is not None else 0

    def _init_schema(self) -> None:
        version = self._read_user_version()
        if version > SCHEMA_VERSION:
            self._closed = True
            self._connection.close()
            raise RuntimeError(
                f"Vault schema {version} is newer than this RedScribe build "
                f"({SCHEMA_VERSION}). Upgrade RedScribe to open it."
            )
        validate_migration_chain()
        for migration in migrations_through(SCHEMA_VERSION):
            if migration.version <= version:
                continue
            try:
                self._connection.executescript(
                    f"BEGIN IMMEDIATE;\n{migration.sql}\n"
                    f"PRAGMA user_version = {migration.version};\nCOMMIT;"
                )
            except sqlite3.DatabaseError:
                with contextlib.suppress(sqlite3.DatabaseError):
                    self._connection.execute("ROLLBACK")
                raise
        self._record_migration_history()

    def _record_migration_history(self) -> None:
        exists = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if exists is None:
            return
        applied_at = self._now()
        with self._connection:
            for migration in migrations_through(SCHEMA_VERSION):
                self._connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, name, applied_at) "
                    "VALUES (?, ?, ?)",
                    (migration.version, migration.name, applied_at),
                )

    def _init_fts(self) -> None:
        exists = (
            self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'nodes_fts'"
            ).fetchone()
            is not None
        )
        try:
            self._connection.executescript(f"BEGIN IMMEDIATE;\n{_FTS_SCHEMA}\nCOMMIT;")
            if not exists:
                self._connection.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")
                self._connection.commit()
            self.fts_enabled = True
        except sqlite3.DatabaseError as exc:
            LOGGER.warning("FTS5 is unavailable; falling back to LIKE search: %s", exc)
            with contextlib.suppress(sqlite3.DatabaseError):
                self._connection.execute("ROLLBACK")
            self._cleanup_fts()
            self.fts_enabled = False

    def _cleanup_fts(self) -> None:
        """Remove partial FTS objects so node writes cannot hit stale triggers."""
        for trigger in _FTS_TRIGGERS:
            with contextlib.suppress(sqlite3.DatabaseError):
                self._connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        with contextlib.suppress(sqlite3.DatabaseError):
            self._connection.execute("DROP TABLE IF EXISTS nodes_fts")
            self._connection.commit()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(sqlite3.DatabaseError):
            self._connection.execute("PRAGMA optimize")
        self._connection.close()

    def _now(self) -> str:
        return utc_now()

    def _row_to_node(self, row: sqlite3.Row) -> Node:
        return Node(
            id=int(row["id"]),
            parent_id=cast(int | None, row["parent_id"]),
            title=str(row["title"]),
            kind=str(row["kind"]),
            content=str(row["content"]),
            tags=str(row["tags"]),
            target=str(row["target"]),
            status=str(row["status"]),
            difficulty=str(row["difficulty"]),
            flag=str(row["flag"]),
            pinned=bool(row["pinned"]),
            sort_order=int(row["sort_order"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            deleted_at=cast(str | None, row["deleted_at"]),
        )

    def _row_to_snippet(self, row: sqlite3.Row) -> Snippet:
        return Snippet(
            id=int(row["id"]),
            title=str(row["title"]),
            command=str(row["command"]),
            description=str(row["description"]),
            tags=str(row["tags"]),
            builtin=False,
        )

    def create_node(
        self,
        title: str,
        parent_id: int | None = None,
        *,
        kind: str = "note",
        content: str = "",
        tags: str = "",
        target: str = "",
        status: str = "todo",
        difficulty: str = "",
        flag: str = "",
        pinned: bool = False,
    ) -> Node:
        """Create a folder or note and return the stored row."""
        if kind not in KINDS:
            raise ValueError(f"Unknown node kind: {kind}")
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status}")
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty: {difficulty}")
        title = title.strip() or "Untitled"
        if contains_control_characters(title):
            raise ValueError("Title contains control characters")
        tags = normalize_tags(tags)
        if parent_id is not None:
            parent = self.get_node(parent_id)
            if parent is None:
                raise ValueError("Parent node does not exist")
            if not parent.is_folder:
                raise ValueError("Notes can only be created inside folders")
        now = self._now()
        sort_order = int(
            self._connection.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM nodes "
                "WHERE parent_id IS ? AND deleted_at IS NULL",
                (parent_id,),
            ).fetchone()[0]
        )
        with self._connection:
            cursor = self._connection.execute(
                "INSERT INTO nodes (parent_id, title, kind, content, tags, target, status, "
                "difficulty, flag, pinned, sort_order, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    parent_id,
                    title,
                    kind,
                    content,
                    tags,
                    target,
                    status,
                    difficulty,
                    flag.strip(),
                    int(pinned),
                    sort_order,
                    now,
                    now,
                ),
            )
        node_id = int(cast(int, cursor.lastrowid))
        created = self.get_node(node_id)
        if created is None:
            raise RuntimeError("Created node could not be read back")
        return created

    def update_node(self, node_id: int, **fields: Any) -> Node:
        """Update mutable node fields and return the new state."""
        unknown = set(fields) - _ALLOWED_UPDATE_FIELDS
        if unknown:
            raise TypeError(f"Unsupported node fields: {', '.join(sorted(unknown))}")
        node = self.get_node(node_id)
        if node is None:
            raise ValueError("Node does not exist")
        if not fields:
            return node

        values: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "title":
                title = str(value).strip() or "Untitled"
                if contains_control_characters(title):
                    raise ValueError("Title contains control characters")
                values[key] = title
            elif key == "status":
                if value not in STATUSES:
                    raise ValueError(f"Unknown status: {value}")
                values[key] = value
            elif key == "difficulty":
                if value not in DIFFICULTIES:
                    raise ValueError(f"Unknown difficulty: {value}")
                values[key] = value
            elif key == "pinned":
                values[key] = int(bool(value))
            elif key == "flag":
                flag = str(value).strip()
                if contains_control_characters(flag):
                    raise ValueError("Flag contains control characters")
                values[key] = flag
            elif key == "tags":
                values[key] = normalize_tags("" if value is None else str(value))
            elif key == "target":
                target = str(value).strip() if value is not None else ""
                if contains_control_characters(target):
                    raise ValueError("Target contains control characters")
                values[key] = target
            else:
                values[key] = "" if value is None else str(value)
        values["updated_at"] = self._now()

        # Snapshot the pre-update state for the version history. Metadata
        # changes are small by nature, so they must never be debounced away.
        metadata = ("title", "tags", "target", "status", "difficulty", "flag")
        tracked = ("content", *metadata)
        if any(key in fields for key in tracked):
            self._snapshot(node, force=any(key in fields for key in metadata))

        assignments = ", ".join(f"{column} = ?" for column in values)
        parameters = [*values.values(), node_id]
        with self._connection:
            self._connection.execute(
                f"UPDATE nodes SET {assignments} WHERE id = ? AND deleted_at IS NULL",
                parameters,
            )
        updated = self.get_node(node_id)
        if updated is None:
            raise RuntimeError("Updated node could not be read back")
        return updated

    def get_node(self, node_id: int, *, include_deleted: bool = False) -> Node | None:
        query = "SELECT * FROM nodes WHERE id = ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        row = self._connection.execute(query, (node_id,)).fetchone()
        return self._row_to_node(row) if row is not None else None

    def children(self, parent_id: int | None, *, include_deleted: bool = False) -> list[Node]:
        query = "SELECT * FROM nodes WHERE parent_id IS ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        query += " ORDER BY sort_order, title COLLATE NOCASE"
        rows = self._connection.execute(query, (parent_id,)).fetchall()
        return [self._row_to_node(row) for row in rows]

    def live_nodes(self) -> list[Node]:
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE deleted_at IS NULL "
            "ORDER BY parent_id, sort_order, title COLLATE NOCASE"
        ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def path_of(self, node_id: int, *, include_self: bool = True, sep: str = " / ") -> str:
        titles: list[str] = []
        current_id: int | None = node_id
        guard = 0
        if not include_self:
            node = self.get_node(node_id, include_deleted=True)
            current_id = node.parent_id if node is not None else None
        while current_id is not None and guard < 100:
            node = self.get_node(current_id, include_deleted=True)
            if node is None:
                break
            titles.append(node.title)
            current_id = node.parent_id
            guard += 1
        return sep.join(reversed(titles))

    def search(self, query: str, *, limit: int = 50) -> list[SearchHit]:
        """Full-text search with a LIKE fallback for systems without FTS5."""
        cleaned = query.strip()
        if not cleaned:
            return []
        if self.fts_enabled and re.search(r"\w", cleaned, re.UNICODE):
            try:
                return self._search_fts(cleaned, limit)
            except sqlite3.DatabaseError as exc:
                LOGGER.warning("FTS search failed; switching to LIKE: %s", exc)
                self.fts_enabled = False
        return self._search_like(cleaned, limit)

    def _search_fts(self, query: str, limit: int) -> list[SearchHit]:
        tokens = re.findall(r"\w+", query, re.UNICODE)
        if not tokens:
            return []
        fts_query = " ".join(f'"{token}"*' for token in tokens)
        rows = self._connection.execute(
            "SELECT n.*, bm25(nodes_fts) AS rank, "
            "snippet(nodes_fts, 1, '[', ']', '…', 18) AS matched "
            "FROM nodes_fts JOIN nodes n ON n.id = nodes_fts.rowid "
            "WHERE nodes_fts MATCH ? AND n.deleted_at IS NULL AND n.kind = 'note' "
            "ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        hits: list[SearchHit] = []
        for row in rows:
            snippet = collapse_whitespace(str(row["matched"] or ""))
            content = str(row["content"])
            if "[" not in snippet or "]" not in snippet:
                snippet = self._excerpt(content, query)
            if not snippet:
                tags = str(row["tags"]).strip()
                snippet = f"tags: {tags}" if tags else "No text preview"
            hits.append(
                SearchHit(
                    node_id=int(row["id"]),
                    title=str(row["title"]),
                    path=self.path_of(int(row["id"]), include_self=False),
                    snippet=snippet,
                    rank=float(row["rank"] or 0.0),
                )
            )
        return hits

    def _search_like(self, query: str, limit: int) -> list[SearchHit]:
        # Escape LIKE wildcards so user input is matched literally.
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE deleted_at IS NULL AND kind = 'note' "
            "AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' "
            "OR tags LIKE ? ESCAPE '\\') "
            "ORDER BY updated_at DESC LIMIT ?",
            (pattern, pattern, pattern, limit),
        ).fetchall()
        hits: list[SearchHit] = []
        for row in rows:
            node = self._row_to_node(row)
            snippet = self._excerpt(node.content, query)
            if not snippet:
                snippet = f"tags: {node.tags}" if node.tags else node.target
            if not snippet:
                snippet = "No text preview"
            hits.append(
                SearchHit(
                    node_id=node.id,
                    title=node.title,
                    path=self.path_of(node.id, include_self=False),
                    snippet=snippet,
                )
            )
        return hits

    def _excerpt(self, content: str, query: str) -> str:
        flat = collapse_whitespace(content)
        if not flat:
            return ""
        needle = query.strip()
        index = flat.casefold().find(needle.casefold())
        if index < 0:
            first = re.findall(r"\w+", needle)
            if first:
                index = flat.casefold().find(first[0].casefold())
        if index < 0:
            return truncate(flat, 180)
        start = max(0, index - 55)
        end = min(len(flat), index + len(needle) + 110)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(flat) else ""
        marked = flat[start:index] + "[" + flat[index : index + len(needle)] + "]"
        return prefix + marked + flat[index + len(needle) : end] + suffix

    def recent_notes(self, limit: int = 8) -> list[Node]:
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE kind = 'note' AND deleted_at IS NULL "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def pinned_notes(self, limit: int = 20) -> list[Node]:
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE kind = 'note' AND deleted_at IS NULL AND pinned = 1 "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def collected_flags(self, limit: int = 500) -> list[FlagHit]:
        revision = self._connection.total_changes
        cached = self._flag_cache.get(limit)
        if cached is not None and cached[0] == revision:
            return list(cached[1])
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE kind = 'note' AND deleted_at IS NULL "
            "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        hits: list[FlagHit] = []
        seen: set[str] = set()
        for row in rows:
            node = self._row_to_node(row)
            values: list[str] = []
            if node.flag:
                values.append(node.flag)
            values.extend(find_flags(node.content))
            for flag in values:
                if flag in seen:
                    continue
                seen.add(flag)
                hits.append(
                    FlagHit(
                        flag=flag,
                        node_id=node.id,
                        title=node.title,
                        path=self.path_of(node.id, include_self=False),
                        manual=flag == node.flag,
                    )
                )
        self._flag_cache[limit] = (revision, hits)
        return list(hits)

    def tag_counts(self) -> list[TagCount]:
        revision = self._connection.total_changes
        if self._tag_cache is not None and self._tag_cache[0] == revision:
            return list(self._tag_cache[1])
        rows = self._connection.execute(
            "SELECT tags FROM nodes WHERE kind = 'note' AND deleted_at IS NULL AND tags <> ''"
        ).fetchall()
        counts: dict[str, int] = {}
        display: dict[str, str] = {}
        for row in rows:
            note_tags: set[str] = set()
            for raw in str(row["tags"]).split(","):
                tag = raw.strip()
                if not tag:
                    continue
                key = tag.casefold()
                if key in note_tags:
                    continue
                note_tags.add(key)
                counts[key] = counts.get(key, 0) + 1
                display.setdefault(key, tag)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], display[item[0]].casefold()))
        counts_list = [TagCount(display[key], count) for key, count in ordered]
        self._tag_cache = (revision, counts_list)
        return list(counts_list)

    def basic_stats(self) -> VaultStats:
        """Return node counts without scanning note bodies for flags or tags."""
        rows = self._connection.execute(
            "SELECT kind, COUNT(*) AS count FROM nodes WHERE deleted_at IS NULL GROUP BY kind"
        ).fetchall()
        counts = {str(row["kind"]): int(row["count"]) for row in rows}
        targets = int(
            self._connection.execute(
                "SELECT COUNT(DISTINCT target) FROM nodes "
                "WHERE deleted_at IS NULL AND kind = 'note' AND target <> ''"
            ).fetchone()[0]
        )
        trashed = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM nodes WHERE deleted_at IS NOT NULL"
            ).fetchone()[0]
        )
        pinned = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM nodes WHERE kind = 'note' "
                "AND deleted_at IS NULL AND pinned = 1"
            ).fetchone()[0]
        )
        return VaultStats(
            notes=counts.get("note", 0),
            folders=counts.get("folder", 0),
            targets=targets,
            pinned=pinned,
            trashed=trashed,
        )

    def _count_flags(self) -> int:
        rows = self._connection.execute(
            "SELECT flag, content FROM nodes WHERE kind = 'note' AND deleted_at IS NULL"
        ).fetchall()
        seen: set[str] = set()
        for row in rows:
            flag = str(row["flag"])
            if flag:
                seen.add(flag)
            seen.update(find_flags(str(row["content"])))
        return len(seen)

    def stats(self) -> VaultStats:
        revision = self._connection.total_changes
        if self._stats_cache is not None and self._stats_cache[0] == revision:
            return self._stats_cache[1]
        base = self.basic_stats()
        stats = VaultStats(
            notes=base.notes,
            folders=base.folders,
            flags=self._count_flags(),
            targets=base.targets,
            tags=len(self.tag_counts()),
            pinned=base.pinned,
            trashed=base.trashed,
        )
        self._stats_cache = (revision, stats)
        return stats

    def duplicate_node(self, node_id: int) -> Node:
        source = self.get_node(node_id)
        if source is None:
            raise ValueError("Node does not exist")
        siblings = self.children(source.parent_id)
        index = next((i for i, node in enumerate(siblings) if node.id == source.id), -1)
        new_sort = source.sort_order + 1
        now = self._now()
        with self._connection:
            self._connection.execute(
                "UPDATE nodes SET sort_order = sort_order + 1 "
                "WHERE parent_id IS ? AND deleted_at IS NULL AND sort_order >= ?",
                (source.parent_id, new_sort),
            )
            new_id = self._clone_subtree(
                source,
                source.parent_id,
                new_sort,
                f"{source.title} (copy)",
                now,
            )
        if index < 0:
            LOGGER.debug("Duplicated node %s outside its sibling list", node_id)
        copied = self.get_node(new_id)
        if copied is None:
            raise RuntimeError("Duplicated node could not be read back")
        return copied

    def _clone_subtree(
        self,
        source: Node,
        parent_id: int | None,
        sort_order: int,
        title: str,
        now: str,
    ) -> int:
        cursor = self._connection.execute(
            "INSERT INTO nodes (parent_id, title, kind, content, tags, target, status, "
            "difficulty, flag, pinned, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                parent_id,
                title,
                source.kind,
                source.content,
                source.tags,
                source.target,
                source.status,
                source.difficulty,
                source.flag,
                int(source.pinned),
                sort_order,
                now,
                now,
            ),
        )
        new_id = int(cast(int, cursor.lastrowid))
        for child in self.children(source.id):
            self._clone_subtree(child, new_id, child.sort_order, child.title, now)
        return new_id

    def move_node(
        self, node_id: int, new_parent_id: int | None, before_id: int | None = None
    ) -> Node:
        """Move a node into a folder or reorder it before a sibling."""
        node = self.get_node(node_id)
        if node is None:
            raise ValueError("Node does not exist")
        if new_parent_id is not None:
            parent = self.get_node(new_parent_id)
            if parent is None:
                raise ValueError("Target parent does not exist")
            if not parent.is_folder:
                raise ValueError("Target parent must be a folder")
            if new_parent_id == node_id or self._is_descendant(new_parent_id, node_id):
                raise ValueError("Cannot move a folder into itself")
        if before_id == node_id:
            return node

        old_parent_id = node.parent_id
        with self._connection:
            if old_parent_id != new_parent_id:
                self._connection.execute(
                    "UPDATE nodes SET parent_id = ?, updated_at = ? WHERE id = ?",
                    (new_parent_id, self._now(), node_id),
                )
            target_rows = self._connection.execute(
                "SELECT id FROM nodes WHERE parent_id IS ? AND deleted_at IS NULL "
                "AND id <> ? ORDER BY sort_order, title COLLATE NOCASE",
                (new_parent_id, node_id),
            ).fetchall()
            target_ids = [int(row["id"]) for row in target_rows]
            if before_id is None:
                target_ids.append(node_id)
            else:
                if before_id not in target_ids:
                    raise ValueError("Reference sibling is not in the target folder")
                target_ids.insert(target_ids.index(before_id), node_id)
            for position, identifier in enumerate(target_ids):
                self._connection.execute(
                    "UPDATE nodes SET sort_order = ? WHERE id = ?",
                    (position, identifier),
                )
            if old_parent_id != new_parent_id:
                old_rows = self._connection.execute(
                    "SELECT id FROM nodes WHERE parent_id IS ? AND deleted_at IS NULL "
                    "ORDER BY sort_order, title COLLATE NOCASE",
                    (old_parent_id,),
                ).fetchall()
                for position, row in enumerate(old_rows):
                    self._connection.execute(
                        "UPDATE nodes SET sort_order = ? WHERE id = ?",
                        (position, int(row["id"])),
                    )
        moved = self.get_node(node_id)
        if moved is None:
            raise RuntimeError("Moved node could not be read back")
        return moved

    def reorder_node(self, node_id: int, offset: int) -> Node | None:
        node = self.get_node(node_id)
        if node is None or offset == 0:
            return node
        siblings = self.children(node.parent_id)
        identifiers = [item.id for item in siblings]
        if node_id not in identifiers:
            return node
        current = identifiers.index(node_id)
        target = max(0, min(len(identifiers) - 1, current + offset))
        if target == current:
            return node
        identifiers.pop(current)
        identifiers.insert(target, node_id)
        with self._connection:
            for position, identifier in enumerate(identifiers):
                self._connection.execute(
                    "UPDATE nodes SET sort_order = ? WHERE id = ?",
                    (position, identifier),
                )
        return self.get_node(node_id)

    def _is_descendant(self, candidate_id: int, ancestor_id: int) -> bool:
        current: int | None = candidate_id
        guard = 0
        while current is not None and guard < 100:
            if current == ancestor_id:
                return True
            node = self.get_node(current, include_deleted=True)
            current = node.parent_id if node is not None else None
            guard += 1
        return False

    def delete_node(self, node_id: int, *, permanent: bool = False) -> int:
        """Move a node and its descendants to the trash, or delete permanently."""
        node = self.get_node(node_id, include_deleted=permanent)
        if node is None:
            raise ValueError("Node does not exist")
        subtree_sql = (
            "WITH RECURSIVE subtree(id) AS ("
            "SELECT id FROM nodes WHERE id = ? "
            "UNION ALL "
            "SELECT n.id FROM nodes n JOIN subtree s ON n.parent_id = s.id"
            ") "
        )
        affected = int(
            self._connection.execute(
                subtree_sql + "SELECT COUNT(*) FROM subtree", (node_id,)
            ).fetchone()[0]
        )
        with self._connection:
            if permanent:
                self._connection.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            else:
                self._connection.execute(
                    subtree_sql
                    + "UPDATE nodes SET deleted_at = ? WHERE id IN (SELECT id FROM subtree)",
                    (node_id, self._now()),
                )
        return affected

    def restore_node(self, node_id: int) -> Node:
        node = self.get_node(node_id, include_deleted=True)
        if node is None:
            raise ValueError("Node does not exist")
        if node.deleted_at is None:
            return node
        with self._connection:
            self._connection.execute(
                "WITH RECURSIVE subtree(id) AS ("
                "SELECT id FROM nodes WHERE id = ? "
                "UNION ALL "
                "SELECT n.id FROM nodes n JOIN subtree s ON n.parent_id = s.id"
                ") UPDATE nodes SET deleted_at = NULL WHERE id IN (SELECT id FROM subtree)",
                (node_id,),
            )
            if node.parent_id is not None:
                parent = self.get_node(node.parent_id, include_deleted=True)
                if parent is None or parent.deleted_at is not None:
                    next_order = int(
                        self._connection.execute(
                            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM nodes "
                            "WHERE parent_id IS NULL AND deleted_at IS NULL"
                        ).fetchone()[0]
                    )
                    self._connection.execute(
                        "UPDATE nodes SET parent_id = NULL, sort_order = ? WHERE id = ?",
                        (next_order, node_id),
                    )
        restored = self.get_node(node_id)
        if restored is None:
            raise RuntimeError("Restored node could not be read back")
        return restored

    def trashed_roots(self) -> list[Node]:
        rows = self._connection.execute(
            "SELECT * FROM nodes n WHERE n.deleted_at IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM nodes p WHERE p.id = n.parent_id "
            "AND p.deleted_at IS NOT NULL) "
            "ORDER BY n.deleted_at DESC"
        ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def empty_trash(self) -> int:
        affected = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM nodes WHERE deleted_at IS NOT NULL"
            ).fetchone()[0]
        )
        with self._connection:
            self._connection.execute("DELETE FROM nodes WHERE deleted_at IS NOT NULL")
        return affected

    def tag_nodes(self, tag: str) -> list[Node]:
        needle = tag.strip().casefold()
        if not needle:
            return []
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE kind = 'note' AND deleted_at IS NULL "
            "ORDER BY updated_at DESC"
        ).fetchall()
        nodes = [self._row_to_node(row) for row in rows]
        return [node for node in nodes if needle in {value.casefold() for value in node.tag_list}]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        before = self._connection.total_changes
        with self._connection:
            self._connection.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        self._settings_changes += self._connection.total_changes - before

    def get_json_setting(self, key: str, default: T) -> T:
        raw = self.get_setting(key)
        if raw is None:
            return default
        try:
            return cast(T, json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            return default

    def set_json_setting(self, key: str, value: Any) -> None:
        self.set_setting(key, json.dumps(value, ensure_ascii=False))

    def list_custom_snippets(self) -> list[Snippet]:
        rows = self._connection.execute(
            "SELECT * FROM snippets ORDER BY title COLLATE NOCASE"
        ).fetchall()
        return [self._row_to_snippet(row) for row in rows]

    def create_snippet(
        self, title: str, command: str, description: str = "", tags: str = ""
    ) -> Snippet:
        title = title.strip() or "Untitled snippet"
        command = command.strip()
        if not command:
            raise ValueError("A snippet needs a command")
        now = self._now()
        with self._connection:
            cursor = self._connection.execute(
                "INSERT INTO snippets(title, command, description, tags, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (title, command, description.strip(), tags.strip(), now, now),
            )
        snippet_id = int(cast(int, cursor.lastrowid))
        return Snippet(
            id=snippet_id,
            title=title,
            command=command,
            description=description.strip(),
            tags=tags.strip(),
        )

    def update_snippet(
        self,
        snippet_id: int,
        *,
        title: str,
        command: str,
        description: str = "",
        tags: str = "",
    ) -> Snippet:
        title = title.strip() or "Untitled snippet"
        command = command.strip()
        if not command:
            raise ValueError("A snippet needs a command")
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE snippets SET title = ?, command = ?, description = ?, tags = ?, "
                "updated_at = ? WHERE id = ?",
                (title, command, description.strip(), tags.strip(), self._now(), snippet_id),
            )
        if cursor.rowcount == 0:
            raise ValueError("Snippet does not exist")
        return Snippet(
            id=snippet_id,
            title=title,
            command=command,
            description=description.strip(),
            tags=tags.strip(),
        )

    def delete_snippet(self, snippet_id: int) -> bool:
        with self._connection:
            cursor = self._connection.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        return cursor.rowcount > 0

    def rebuild_search_index(self) -> None:
        if not self.fts_enabled:
            return
        with self._connection:
            self._connection.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")

    # ------------------------------------------------------------------
    # Platform events, audit, and idempotency
    # ------------------------------------------------------------------

    def record_event(
        self,
        *,
        kind: str,
        entity_type: str,
        entity_id: int | None = None,
        action: str,
        payload: object | None = None,
        request_id: str = "",
        now: str | datetime | None = None,
    ) -> storage_events.EntityEvent:
        return storage_events.record_event(
            self._connection,
            kind=kind,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=payload,
            request_id=request_id,
            now=now,
        )

    def list_events(
        self,
        *,
        since_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        limit: int = 100,
    ) -> list[storage_events.EntityEvent]:
        return storage_events.list_events(
            self._connection,
            since_id=since_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )

    def record_request(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        outcome: str,
        duration_ms: float = 0.0,
        client: str = "",
        now: str | datetime | None = None,
    ) -> None:
        storage_events.record_request_audit(
            self._connection,
            request_id=request_id,
            method=method,
            path=path,
            outcome=outcome,
            duration_ms=duration_ms,
            client=client,
            now=now,
        )

    def list_request_audit(self, *, limit: int = 100) -> list[dict[str, object]]:
        return storage_events.list_request_audit(self._connection, limit=limit)

    def idempotency_get(self, key: str) -> storage_idempotency.IdempotencyRecord | None:
        return storage_idempotency.get_record(self._connection, key)

    def idempotency_put(
        self,
        *,
        key: str,
        method: str,
        request_hash: str,
        status: int,
        response: dict[str, object],
        ttl_seconds: int = 86400,
        now: str | datetime | None = None,
    ) -> storage_idempotency.IdempotencyRecord:
        return storage_idempotency.put_record(
            self._connection,
            key=key,
            method=method,
            request_hash=request_hash,
            status=status,
            response=response,
            ttl_seconds=ttl_seconds,
            now=now,
        )

    def idempotency_prune(self, *, now: str | datetime | None = None) -> int:
        return storage_idempotency.prune_expired(self._connection, now=now)

    def integrity_report(self, *, json_keys: Iterable[str] = ()) -> IntegrityReport:
        """Return a deterministic, sorted snapshot of vault health issues."""
        return scan_integrity(
            self._connection,
            schema_version=self.schema_version,
            fts_enabled=self.fts_enabled,
            json_keys=json_keys,
        )

    def index_drift(self) -> IndexDrift:
        """Return row-level differences between the nodes table and FTS index."""
        if not self.fts_enabled:
            return IndexDrift()
        return index_drift(self._connection, triggers=_FTS_TRIGGERS)

    def repair_index(self) -> IndexRepairResult:
        """Rebuild FTS data and restore triggers only when drift is present."""
        if not self.fts_enabled:
            return IndexRepairResult()
        drift = index_drift(self._connection, triggers=_FTS_TRIGGERS)
        if drift.clean:
            return IndexRepairResult()
        rows_fixed = drift.rows
        triggers_restored = len(drift.missing_triggers)
        if drift.missing_index or drift.missing_triggers:
            self._connection.executescript(_FTS_SCHEMA)
        if drift.missing_index or drift.corrupt or rows_fixed:
            with self._connection:
                self._connection.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")
        remaining = index_drift(self._connection, triggers=_FTS_TRIGGERS)
        if not remaining.clean:
            LOGGER.warning("FTS index still reports drift after repair")
        return IndexRepairResult(
            rebuilt=bool(drift.missing_index or drift.corrupt or rows_fixed),
            rows_fixed=rows_fixed,
            triggers_restored=triggers_restored,
            remaining_drift=remaining.rows,
        )

    # ------------------------------------------------------------------
    # Version history
    # ------------------------------------------------------------------

    HISTORY_KEEP = 100
    HISTORY_MIN_AGE_SECONDS = 120
    HISTORY_MIN_CHAR_DELTA = 128
    _HISTORY_METADATA = ("title", "tags", "target", "status", "difficulty", "flag")

    def _snapshot(self, node: Node, *, force: bool = False) -> None:
        row = self._connection.execute(
            "SELECT id, title, content, tags, target, status, difficulty, flag, created_at "
            "FROM nodes_history WHERE node_id = ? ORDER BY id DESC LIMIT 1",
            (node.id,),
        ).fetchone()
        if row is not None:
            same = (
                row["title"] == node.title
                and row["content"] == node.content
                and row["tags"] == node.tags
                and row["target"] == node.target
                and row["status"] == node.status
                and row["difficulty"] == node.difficulty
                and row["flag"] == node.flag
            )
            if same:
                return
            metadata_changed = any(
                str(row[field]) != str(getattr(node, field)) for field in self._HISTORY_METADATA
            )
            if not force and not metadata_changed:
                try:
                    raw = str(row["created_at"]).replace("Z", "+00:00")
                    created = datetime.fromisoformat(raw)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - created).total_seconds()
                except (ValueError, TypeError):
                    age = self.HISTORY_MIN_AGE_SECONDS + 1
                old_content = str(row["content"])
                delta = abs(len(node.content) - len(old_content))
                if delta == 0 and node.content != old_content:
                    delta = self.HISTORY_MIN_CHAR_DELTA
                if age < self.HISTORY_MIN_AGE_SECONDS and delta < self.HISTORY_MIN_CHAR_DELTA:
                    return
        with self._connection:
            self._connection.execute(
                "INSERT INTO nodes_history (node_id, title, content, tags, target, status, "
                "difficulty, flag, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    node.id,
                    node.title,
                    node.content,
                    node.tags,
                    node.target,
                    node.status,
                    node.difficulty,
                    node.flag,
                    self._now(),
                ),
            )
            self._connection.execute(
                "DELETE FROM nodes_history WHERE node_id = ? AND id NOT IN ("
                "  SELECT id FROM nodes_history WHERE node_id = ? ORDER BY id DESC LIMIT ?"
                ")",
                (node.id, node.id, self.HISTORY_KEEP),
            )

    def list_versions(self, node_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, created_at, title, status, length(content) AS chars "
            "FROM nodes_history WHERE node_id = ? ORDER BY id DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "created_at": str(row["created_at"]),
                "title": str(row["title"]),
                "status": str(row["status"]),
                "chars": int(row["chars"]),
            }
            for row in rows
        ]

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT id, node_id, title, content, tags, target, status, difficulty, flag, "
            "created_at "
            "FROM nodes_history WHERE id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "node_id": int(row["node_id"]),
            "title": str(row["title"]),
            "content": str(row["content"]),
            "tags": str(row["tags"]),
            "target": str(row["target"]),
            "status": str(row["status"]),
            "difficulty": str(row["difficulty"]),
            "flag": str(row["flag"]),
            "created_at": str(row["created_at"]),
        }

    def restore_version(self, version_id: int) -> Node:
        entry = self.get_version(version_id)
        if entry is None:
            raise ValueError("Version does not exist")
        node = self.get_node(int(entry["node_id"]))
        if node is None:
            raise ValueError("Node does not exist")
        self._snapshot(node, force=True)
        with self._connection:
            self._connection.execute(
                "UPDATE nodes SET title = ?, content = ?, tags = ?, target = ?, status = ?, "
                "difficulty = ?, flag = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (
                    str(entry["title"]),
                    str(entry["content"]),
                    normalize_tags(str(entry["tags"])),
                    str(entry["target"]),
                    str(entry["status"]),
                    str(entry["difficulty"]),
                    str(entry["flag"]),
                    self._now(),
                    node.id,
                ),
            )
        restored = self.get_node(node.id)
        if restored is None:
            raise RuntimeError("Restored node could not be read back")
        return restored

    def prune_versions(self, keep: int) -> PruneResult:
        """Keep the newest ``keep`` versions per node and drop the rest."""
        if keep < 0:
            raise ValueError("keep must be non-negative")
        with self._connection:
            orphan_cursor = self._connection.execute(
                "DELETE FROM nodes_history WHERE node_id NOT IN (SELECT id FROM nodes)"
            )
            orphan_removed = max(0, orphan_cursor.rowcount)
            node_ids = [
                int(row[0])
                for row in self._connection.execute(
                    "SELECT DISTINCT node_id FROM nodes_history ORDER BY node_id"
                )
            ]
            removed = 0
            affected = 0
            for node_id in node_ids:
                cursor = self._connection.execute(
                    "DELETE FROM nodes_history WHERE node_id = ? AND id NOT IN ("
                    "  SELECT id FROM nodes_history WHERE node_id = ? ORDER BY id DESC LIMIT ?"
                    ")",
                    (node_id, node_id, keep),
                )
                count = max(0, cursor.rowcount)
                if count:
                    removed += count
                    affected += 1
        return PruneResult(
            versions_removed=removed,
            nodes_affected=affected,
            orphan_versions_removed=orphan_removed,
        )

    def paths_map(self, *, include_self: bool = True) -> dict[int, str]:
        """Return ``{node_id: path}`` for every node in one pass (no per-node queries)."""
        rows = self._connection.execute("SELECT id, parent_id, title FROM nodes").fetchall()
        titles: dict[int, str] = {int(row["id"]): str(row["title"]) for row in rows}
        parents: dict[int, int | None] = {
            int(row["id"]): (int(row["parent_id"]) if row["parent_id"] is not None else None)
            for row in rows
        }
        cache: dict[int, str] = {}

        def path_of(node_id: int) -> str:
            cached = cache.get(node_id)
            if cached is not None:
                return cached
            chain: list[str] = []
            current: int | None = node_id if include_self else parents.get(node_id)
            guard = 0
            while current is not None and guard < 100:
                title = titles.get(current)
                if title is None:
                    break
                chain.append(title)
                current = parents.get(current)
                guard += 1
            result = " / ".join(reversed(chain))
            cache[node_id] = result
            return result

        return {node_id: path_of(node_id) for node_id in titles}

    def backup_to_auto(self, max_backups: int | None = None) -> Path:
        """Write an automatic backup next to the vault before destructive actions.

        The filename carries a full ``YYYYMMDDTHHMMSSZ`` timestamp and, if that
        already exists, a numeric suffix, so a backup is never silently
        overwritten by a later one within the same second. When ``max_backups``
        is set, only automatic backups are rotated; user-named backups are kept.
        """
        if max_backups is not None and max_backups < 1:
            raise ValueError("max_backups must be at least 1")
        if self.path is None:
            directory = Path(tempfile.gettempdir()) / "redscribe-backups"
        else:
            directory = Path(self.path).resolve().parent / "backups"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = directory / f"vault-{stamp}.db"
        counter = 1
        while target.exists():
            target = directory / f"vault-{stamp}-{counter}.db"
            counter += 1
        self.backup_to(target)
        if max_backups is not None:
            rotate_auto_backups(directory, keep=max_backups, exclude=target)
        return target

    def backup_to(self, destination: str | Path) -> Path:
        """Write a consistent copy of the vault using SQLite's backup API."""
        target = Path(destination).expanduser()
        if self.path is not None and target.resolve() == self.path.resolve():
            raise ValueError("Backup destination is the open vault")
        target.parent.mkdir(parents=True, exist_ok=True)
        destination_connection = sqlite3.connect(str(target))
        try:
            with destination_connection:
                self._connection.backup(destination_connection)
        finally:
            destination_connection.close()
        return target

    def backup_bytes(self) -> bytes:
        """Return a consistent, binary copy of the vault for downloading."""
        with tempfile.TemporaryDirectory(prefix="redscribe-backup-") as directory:
            target = self.backup_to(Path(directory) / "vault.db")
            return target.read_bytes()

    def checkpoint(self, *, mode: str = "TRUNCATE") -> CheckpointResult:
        """Checkpoint the write-ahead log and return SQLite's counters."""
        normalized = validate_checkpoint_mode(mode)
        row = self._connection.execute(f"PRAGMA wal_checkpoint({normalized})").fetchone()
        if row is None:
            return CheckpointResult(mode=normalized, busy=0, log=0, checkpointed=0)
        return CheckpointResult(
            mode=normalized,
            busy=int(row[0]),
            log=int(row[1]),
            checkpointed=int(row[2]),
        )

    def optimize(self) -> None:
        """Refresh SQLite's query planner statistics for this vault."""
        self._connection.execute("PRAGMA optimize")

    def iter_notes(self) -> Iterator[Node]:
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE kind = 'note' AND deleted_at IS NULL "
            "ORDER BY updated_at DESC"
        ).fetchall()
        for row in rows:
            yield self._row_to_node(row)

    def node_filename(self, node_id: int) -> str:
        node = self.get_node(node_id)
        title = node.title if node is not None else f"note-{node_id}"
        return f"{slugify(title, fallback=f'note-{node_id}')}.md"
