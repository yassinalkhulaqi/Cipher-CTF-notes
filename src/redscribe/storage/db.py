"""SQLite-backed vault storage for notes, folders, settings, and snippets."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import sqlite3
from collections.abc import Iterator
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

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")

SCHEMA_VERSION = 2

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

_MIGRATIONS: dict[int, str] = {
    1: _MIGRATION_1,
    2: _MIGRATION_2,
}

_FTS_TRIGGERS = ("nodes_fts_ai", "nodes_fts_ad", "nodes_fts_au")

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
        self._configure()
        self._init_schema()
        self.fts_enabled = False
        if enable_fts:
            self._init_fts()

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
        for target in range(version + 1, SCHEMA_VERSION + 1):
            script = _MIGRATIONS.get(target)
            if script is None:
                raise RuntimeError(f"Missing SQLite migration {target}")
            try:
                self._connection.executescript(
                    f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {target};\nCOMMIT;"
                )
            except sqlite3.DatabaseError:
                with contextlib.suppress(sqlite3.DatabaseError):
                    self._connection.execute("ROLLBACK")
                raise

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
                values[key] = str(value).strip() or "Untitled"
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
                values[key] = str(value).strip()
            else:
                values[key] = "" if value is None else str(value)
        values["updated_at"] = self._now()

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
        pattern = f"%{query}%"
        rows = self._connection.execute(
            "SELECT * FROM nodes WHERE deleted_at IS NULL AND kind = 'note' "
            "AND (title LIKE ? OR content LIKE ? OR tags LIKE ?) "
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
        return hits

    def tag_counts(self) -> list[TagCount]:
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
        return [TagCount(display[key], count) for key, count in ordered]

    def stats(self) -> VaultStats:
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
            flags=len(self.collected_flags()),
            targets=targets,
            tags=len(self.tag_counts()),
            pinned=pinned,
            trashed=trashed,
        )

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
        with self._connection:
            self._connection.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

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
