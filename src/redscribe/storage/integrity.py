"""Integrity diagnostics for the SQLite vault."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from redscribe.domain.utils import slugify

FTS_TRIGGERS: tuple[str, ...] = ("nodes_fts_ai", "nodes_fts_ad", "nodes_fts_au")

ISSUE_CODES: tuple[str, ...] = (
    "missing_parent",
    "orphan_node",
    "cycle",
    "fts_corrupt",
    "fts_missing_index",
    "fts_missing_trigger",
    "fts_drift",
    "invalid_tag",
    "duplicate_slug",
    "invalid_json_setting",
)

_ERROR_CODES = frozenset({"missing_parent", "cycle", "fts_corrupt", "fts_missing_index"})
_VERIFY_TABLE = "nodes_fts_verify"
_VERIFY_SAVEPOINT = "redscribe_fts_verify"
_CHECK_SAVEPOINT = "redscribe_fts_check"
_REPORT_IDS = 10
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_PROBE_TOKENS = 12


def normalize_tags(raw: str) -> str:
    """Normalize a comma-separated tag list.

    Trims each tag, collapses internal whitespace, drops empties, and
    de-duplicates case-insensitively (first occurrence wins). The stored
    format stays human-readable ``a, b, c``.
    """
    seen: set[str] = set()
    tags: list[str] = []
    for piece in raw.split(","):
        normalized = re.sub(r"\s+", " ", piece).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(normalized)
    return ", ".join(tags)


def contains_control_characters(value: str) -> bool:
    """Return whether a single-line field carries control characters."""
    return any(ord(character) < 32 and character not in "\t" for character in value)


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    """One deterministic finding from a vault integrity scan."""

    code: str
    message: str
    severity: str = "warning"
    node_id: int | None = None
    key: str | None = None
    related_ids: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "node_id": self.node_id,
            "key": self.key,
            "related_ids": list(self.related_ids),
        }


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """A sorted, serializable snapshot of vault health."""

    issues: tuple[IntegrityIssue, ...] = ()
    nodes_checked: int = 0
    settings_checked: int = 0
    schema_version: int = 0
    fts_enabled: bool = False

    @property
    def ok(self) -> bool:
        return all(issue.severity != "error" for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def codes(self) -> frozenset[str]:
        return frozenset(issue.code for issue in self.issues)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return counts

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "issues": [issue.as_dict() for issue in self.issues],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "nodes_checked": self.nodes_checked,
            "settings_checked": self.settings_checked,
            "schema_version": self.schema_version,
            "fts_enabled": self.fts_enabled,
        }


@dataclass(frozen=True, slots=True)
class IndexDrift:
    """Differences between the nodes table and the FTS index."""

    missing_ids: tuple[int, ...] = ()
    stale_ids: tuple[int, ...] = ()
    changed_ids: tuple[int, ...] = ()
    missing_triggers: tuple[str, ...] = ()
    corrupt: bool = False
    missing_index: bool = False

    @property
    def rows(self) -> int:
        return len(self.missing_ids) + len(self.stale_ids) + len(self.changed_ids)

    @property
    def clean(self) -> bool:
        return (
            self.rows == 0
            and not self.missing_triggers
            and not self.corrupt
            and not self.missing_index
        )


@dataclass(frozen=True, slots=True)
class IndexRepairResult:
    """Outcome of a deterministic FTS index repair."""

    rebuilt: bool = False
    rows_fixed: int = 0
    triggers_restored: int = 0
    remaining_drift: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "rebuilt": self.rebuilt,
            "rows_fixed": self.rows_fixed,
            "triggers_restored": self.triggers_restored,
            "remaining_drift": self.remaining_drift,
        }


def sort_issues(issues: Iterable[IntegrityIssue]) -> tuple[IntegrityIssue, ...]:
    order = {code: position for position, code in enumerate(ISSUE_CODES)}
    return tuple(
        sorted(
            issues,
            key=lambda issue: (
                order.get(issue.code, len(ISSUE_CODES)),
                issue.node_id if issue.node_id is not None else -1,
                issue.key or "",
                issue.message,
                issue.related_ids,
            ),
        )
    )


def _issue(
    code: str,
    message: str,
    *,
    node_id: int | None = None,
    key: str | None = None,
    related_ids: tuple[int, ...] = (),
) -> IntegrityIssue:
    severity = "error" if code in _ERROR_CODES else "warning"
    return IntegrityIssue(
        code=code,
        message=message,
        severity=severity,
        node_id=node_id,
        key=key,
        related_ids=related_ids,
    )


def _find_cycles(parents: dict[int, int | None]) -> list[tuple[int, ...]]:
    cycles: dict[frozenset[int], tuple[int, ...]] = {}
    resolved: set[int] = set()
    for start in sorted(parents):
        if start in resolved:
            continue
        stack: list[int] = []
        positions: dict[int, int] = {}
        current = start
        while current in parents and current not in resolved:
            if current in positions:
                members = frozenset(stack[positions[current] :])
                cycles.setdefault(members, tuple(sorted(members)))
                break
            positions[current] = len(stack)
            stack.append(current)
            parent = parents[current]
            if parent is None:
                break
            current = parent
        resolved.update(stack)
    return sorted(cycles.values())


def _structural_issues(connection: sqlite3.Connection) -> tuple[list[IntegrityIssue], int]:
    rows = connection.execute(
        "SELECT id, parent_id, kind, deleted_at FROM nodes ORDER BY id"
    ).fetchall()
    nodes = {int(row["id"]): row for row in rows}
    parents: dict[int, int | None] = {}
    for node_id, row in nodes.items():
        parent_id = row["parent_id"]
        parents[node_id] = int(parent_id) if parent_id is not None else None

    issues: list[IntegrityIssue] = []
    for node_id in sorted(nodes):
        parent_id = parents[node_id]
        if parent_id is None:
            continue
        parent = nodes.get(parent_id)
        row = nodes[node_id]
        if parent is None:
            issues.append(
                _issue(
                    "missing_parent",
                    f"Node {node_id} references missing parent {parent_id}",
                    node_id=node_id,
                    related_ids=(parent_id,),
                )
            )
        elif str(parent["kind"]) != "folder":
            issues.append(
                _issue(
                    "orphan_node",
                    f"Node {node_id} has non-folder parent {parent_id}",
                    node_id=node_id,
                    related_ids=(parent_id,),
                )
            )
        elif row["deleted_at"] is None and parent["deleted_at"] is not None:
            issues.append(
                _issue(
                    "orphan_node",
                    f"Live node {node_id} has a deleted parent {parent_id}",
                    node_id=node_id,
                    related_ids=(parent_id,),
                )
            )

    for members in _find_cycles(parents):
        issues.append(
            _issue(
                "cycle",
                "Parent cycle: " + ", ".join(str(node_id) for node_id in members),
                node_id=members[0],
                related_ids=members,
            )
        )
    return issues, len(nodes)


def _tag_issues(connection: sqlite3.Connection) -> list[IntegrityIssue]:
    rows = connection.execute("SELECT id, tags FROM nodes ORDER BY id").fetchall()
    issues: list[IntegrityIssue] = []
    for row in rows:
        node_id = int(row["id"])
        raw = str(row["tags"])
        if not raw:
            continue
        if raw == normalize_tags(raw) and not contains_control_characters(raw):
            continue
        issues.append(
            _issue(
                "invalid_tag",
                f"Node {node_id} has non-canonical tags",
                node_id=node_id,
            )
        )
    return issues


def _slug_issues(
    connection: sqlite3.Connection, slugger: Callable[[str], str]
) -> list[IntegrityIssue]:
    by_slug: dict[str, list[int]] = {}
    rows = connection.execute(
        "SELECT id, title FROM nodes WHERE deleted_at IS NULL AND kind = 'note' ORDER BY id"
    ).fetchall()
    for row in rows:
        node_id = int(row["id"])
        by_slug.setdefault(slugger(str(row["title"])), []).append(node_id)
    issues: list[IntegrityIssue] = []
    for slug in sorted(by_slug):
        identifiers = tuple(by_slug[slug])
        if len(identifiers) < 2:
            continue
        issues.append(
            _issue(
                "duplicate_slug",
                f"Slug {slug!r} is shared by {len(identifiers)} notes",
                key=slug,
                related_ids=identifiers,
            )
        )
    return issues


def _setting_issues(
    connection: sqlite3.Connection, json_keys: Iterable[str]
) -> tuple[list[IntegrityIssue], int]:
    keys = frozenset(json_keys)
    rows = connection.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    issues: list[IntegrityIssue] = []
    for row in rows:
        key = str(row["key"])
        value = str(row["value"])
        stripped = value.strip()
        looks_json = (
            stripped.startswith(("{", "["))
            or key in keys
            or key.endswith(".json")
            or key.endswith("_json")
        )
        if not looks_json:
            continue
        try:
            json.loads(stripped)
        except (TypeError, json.JSONDecodeError):
            issues.append(
                _issue(
                    "invalid_json_setting",
                    f"Setting {key!r} is not valid JSON",
                    key=key,
                )
            )
    return issues, len(rows)


def _expected_docsize(connection: sqlite3.Connection) -> dict[int, bytes] | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (_VERIFY_TABLE,)
    ).fetchone()
    if exists is not None:
        return None
    connection.execute(f"SAVEPOINT {_VERIFY_SAVEPOINT}")
    try:
        connection.execute(
            f"CREATE VIRTUAL TABLE {_VERIFY_TABLE} USING fts5("
            "title, content, tags, content='nodes', content_rowid='id')"
        )
        connection.execute(f"INSERT INTO {_VERIFY_TABLE}({_VERIFY_TABLE}) VALUES('rebuild')")
        rows = connection.execute(f"SELECT id, sz FROM {_VERIFY_TABLE}_docsize").fetchall()
        result = {int(row["id"]): bytes(row["sz"]) for row in rows}
    except sqlite3.DatabaseError:
        connection.execute(f"ROLLBACK TO SAVEPOINT {_VERIFY_SAVEPOINT}")
        result = None
    else:
        connection.execute(f"DROP TABLE {_VERIFY_TABLE}")
    finally:
        connection.execute(f"RELEASE SAVEPOINT {_VERIFY_SAVEPOINT}")
    return result


def _normalize_token(token: str) -> str:
    decomposed = unicodedata.normalize("NFKD", token)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _probe_tokens(title: str, content: str, tags: str) -> tuple[str, ...]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(" ".join((title, content, tags))):
        token = _normalize_token(match.group(0)).casefold()
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    if len(tokens) <= _PROBE_TOKENS:
        return tuple(tokens)
    step = len(tokens) / _PROBE_TOKENS
    return tuple(
        tokens[min(len(tokens) - 1, int(position * step))] for position in range(_PROBE_TOKENS)
    )


def _probe_drift(connection: sqlite3.Connection, node_ids: set[int]) -> set[int]:
    drifted: set[int] = set()
    if not node_ids:
        return drifted
    rows = connection.execute("SELECT id, title, content, tags FROM nodes").fetchall()
    for row in rows:
        node_id = int(row["id"])
        if node_id not in node_ids:
            continue
        tokens = _probe_tokens(str(row["title"]), str(row["content"]), str(row["tags"]))
        for token in tokens:
            expression = '"' + token.replace('"', '""') + '"'
            found = connection.execute(
                "SELECT rowid FROM nodes_fts WHERE nodes_fts MATCH ? AND rowid = ?",
                (expression, node_id),
            ).fetchone()
            if found is None:
                drifted.add(node_id)
                break
    return drifted


def index_drift(
    connection: sqlite3.Connection, *, triggers: Iterable[str] = FTS_TRIGGERS
) -> IndexDrift:
    exists = (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'nodes_fts'"
        ).fetchone()
        is not None
    )
    if not exists:
        return IndexDrift(missing_index=True, missing_triggers=tuple(triggers))

    names = tuple(triggers)
    missing_triggers = tuple(
        name
        for name in names
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name = ?", (name,)
        ).fetchone()
        is None
    )

    corrupt = False
    connection.execute(f"SAVEPOINT {_CHECK_SAVEPOINT}")
    try:
        connection.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('integrity-check')")
    except sqlite3.DatabaseError:
        corrupt = True
        connection.execute(f"ROLLBACK TO SAVEPOINT {_CHECK_SAVEPOINT}")
    finally:
        connection.execute(f"RELEASE SAVEPOINT {_CHECK_SAVEPOINT}")

    rows = connection.execute("SELECT id, sz FROM nodes_fts_docsize").fetchall()
    actual = {int(row["id"]): bytes(row["sz"]) for row in rows}
    expected = _expected_docsize(connection)
    if expected is None:
        node_ids = {int(row[0]) for row in connection.execute("SELECT id FROM nodes")}
        missing = tuple(sorted(node_ids - actual.keys()))
        stale = tuple(sorted(actual.keys() - node_ids))
        changed: tuple[int, ...] = ()
    else:
        missing = tuple(sorted(expected.keys() - actual.keys()))
        stale = tuple(sorted(actual.keys() - expected.keys()))
        common = expected.keys() & actual.keys()
        size_changed = {node_id for node_id in common if expected[node_id] != actual[node_id]}
        changed = tuple(sorted(size_changed | _probe_drift(connection, set(common))))
    return IndexDrift(
        missing_ids=missing,
        stale_ids=stale,
        changed_ids=changed,
        missing_triggers=missing_triggers,
        corrupt=corrupt,
    )


def _fts_issues(connection: sqlite3.Connection, triggers: Iterable[str]) -> list[IntegrityIssue]:
    drift = index_drift(connection, triggers=triggers)
    issues: list[IntegrityIssue] = []
    if drift.missing_index:
        issues.append(_issue("fts_missing_index", "FTS index table is missing"))
        return issues
    if drift.corrupt:
        issues.append(_issue("fts_corrupt", "FTS index failed its integrity check"))
    if drift.missing_triggers:
        names = ", ".join(drift.missing_triggers)
        issues.append(
            _issue(
                "fts_missing_trigger",
                f"Missing FTS triggers: {names}",
                key=",".join(drift.missing_triggers),
            )
        )
    if drift.rows:
        identifiers = sorted(set(drift.missing_ids + drift.stale_ids + drift.changed_ids))
        issues.append(
            _issue(
                "fts_drift",
                f"FTS index drift: {len(drift.missing_ids)} missing, "
                f"{len(drift.stale_ids)} stale, {len(drift.changed_ids)} changed rows",
                related_ids=tuple(identifiers[:_REPORT_IDS]),
            )
        )
    return issues


def scan_integrity(
    connection: sqlite3.Connection,
    *,
    schema_version: int,
    fts_enabled: bool,
    json_keys: Iterable[str] = (),
    triggers: Iterable[str] = FTS_TRIGGERS,
    slugger: Callable[[str], str] = slugify,
) -> IntegrityReport:
    structural, node_count = _structural_issues(connection)
    issues = list(structural)
    issues.extend(_tag_issues(connection))
    issues.extend(_slug_issues(connection, slugger))
    setting_issues, setting_count = _setting_issues(connection, json_keys)
    issues.extend(setting_issues)
    if fts_enabled:
        issues.extend(_fts_issues(connection, triggers))
    return IntegrityReport(
        issues=sort_issues(issues),
        nodes_checked=node_count,
        settings_checked=setting_count,
        schema_version=schema_version,
        fts_enabled=fts_enabled,
    )
