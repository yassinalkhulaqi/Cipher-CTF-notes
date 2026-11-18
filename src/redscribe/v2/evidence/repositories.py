"""Repositories for evidence records, custody, links, and manifests."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any, Protocol

from redscribe.storage.db import Vault
from redscribe.v2.evidence.errors import RepositoryError
from redscribe.v2.evidence.models import (
    CustodyEvent,
    EvidenceManifest,
    EvidenceRecord,
    FindingLink,
    RetentionPolicy,
)

RECORD_TABLE = "evidence_vault_records"
CUSTODY_TABLE = "evidence_vault_custody"
LINK_TABLE = "evidence_vault_links"
RETENTION_TABLE = "evidence_vault_retention"
MANIFEST_TABLE = "evidence_vault_manifests"


def connection_of(source: Vault | sqlite3.Connection) -> sqlite3.Connection:
    """Return a raw SQLite connection from a vault or a connection."""
    if isinstance(source, sqlite3.Connection):
        return source
    return source.connection


class EvidenceRepository(Protocol):
    """Persistence contract used by :class:`EvidenceVaultService`."""

    def all_records(self) -> list[EvidenceRecord]: ...

    def get_record(self, evidence_id: str) -> EvidenceRecord | None: ...

    def save_record(self, record: EvidenceRecord) -> None: ...

    def delete_record(self, evidence_id: str) -> bool: ...

    def custody_events(self, evidence_id: str = "") -> list[CustodyEvent]: ...

    def save_custody_event(self, event: CustodyEvent) -> None: ...

    def delete_custody(self, evidence_id: str) -> int: ...

    def all_links(self) -> list[FindingLink]: ...

    def save_link(self, link: FindingLink) -> None: ...

    def delete_link(self, link_id: int) -> bool: ...

    def delete_links(self, evidence_id: str) -> int: ...

    def all_policies(self) -> list[RetentionPolicy]: ...

    def save_policy(self, policy: RetentionPolicy) -> None: ...

    def delete_policy(self, evidence_id: str) -> bool: ...

    def all_manifests(self) -> list[EvidenceManifest]: ...

    def save_manifest(self, manifest: EvidenceManifest) -> None: ...


class InMemoryEvidenceRepository:
    """A deterministic in-memory repository for unit tests and previews."""

    def __init__(self, records: Iterable[EvidenceRecord] = ()) -> None:
        self._records = {item.id: item for item in records}
        self._custody: dict[int, CustodyEvent] = {}
        self._links: dict[int, FindingLink] = {}
        self._policies: dict[str, RetentionPolicy] = {}
        self._manifests: list[EvidenceManifest] = []

    def all_records(self) -> list[EvidenceRecord]:
        return [self._records[key] for key in sorted(self._records)]

    def get_record(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def save_record(self, record: EvidenceRecord) -> None:
        self._records[record.id] = record

    def delete_record(self, evidence_id: str) -> bool:
        return self._records.pop(evidence_id, None) is not None

    def custody_events(self, evidence_id: str = "") -> list[CustodyEvent]:
        events = list(self._custody.values())
        if evidence_id:
            events = [item for item in events if item.evidence_id == evidence_id]
        return sorted(events, key=lambda item: item.id)

    def save_custody_event(self, event: CustodyEvent) -> None:
        self._custody[event.id] = event

    def delete_custody(self, evidence_id: str) -> int:
        targets = [item.id for item in self.custody_events(evidence_id)]
        for item_id in targets:
            del self._custody[item_id]
        return len(targets)

    def all_links(self) -> list[FindingLink]:
        return [self._links[key] for key in sorted(self._links)]

    def save_link(self, link: FindingLink) -> None:
        self._links[link.id] = link

    def delete_link(self, link_id: int) -> bool:
        return self._links.pop(link_id, None) is not None

    def delete_links(self, evidence_id: str) -> int:
        targets = [item.id for item in self.all_links() if item.evidence_id == evidence_id]
        for item_id in targets:
            del self._links[item_id]
        return len(targets)

    def all_policies(self) -> list[RetentionPolicy]:
        return [self._policies[key] for key in sorted(self._policies)]

    def save_policy(self, policy: RetentionPolicy) -> None:
        self._policies[policy.evidence_id] = policy

    def delete_policy(self, evidence_id: str) -> bool:
        return self._policies.pop(evidence_id, None) is not None

    def all_manifests(self) -> list[EvidenceManifest]:
        return list(self._manifests)

    def save_manifest(self, manifest: EvidenceManifest) -> None:
        self._manifests.append(manifest)


SCHEMA_STATEMENTS: tuple[str, ...] = (
    f"CREATE TABLE IF NOT EXISTS {RECORD_TABLE} ("
    "evidence_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)",
    f"CREATE TABLE IF NOT EXISTS {CUSTODY_TABLE} ("
    "id INTEGER PRIMARY KEY, evidence_id TEXT NOT NULL, payload TEXT NOT NULL)",
    f"CREATE TABLE IF NOT EXISTS {LINK_TABLE} ("
    "id INTEGER PRIMARY KEY, evidence_id TEXT NOT NULL, payload TEXT NOT NULL)",
    f"CREATE TABLE IF NOT EXISTS {RETENTION_TABLE} ("
    "evidence_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, checksum TEXT NOT NULL, "
    "generated_at TEXT NOT NULL, payload TEXT NOT NULL)",
    f"CREATE INDEX IF NOT EXISTS idx_evidence_custody_item ON {CUSTODY_TABLE}(evidence_id)",
    f"CREATE INDEX IF NOT EXISTS idx_evidence_links_item ON {LINK_TABLE}(evidence_id)",
)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(value: object) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        result: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RepositoryError("Corrupt evidence repository row") from exc
    return dict(result) if isinstance(result, dict) else {}


class SQLiteEvidenceRepository:
    """Repository backed by additive tables in the existing vault database."""

    def __init__(self, source: Vault | sqlite3.Connection) -> None:
        self._connection = connection_of(source)
        self._init_schema()

    def _init_schema(self) -> None:
        try:
            with self._connection:
                for statement in SCHEMA_STATEMENTS:
                    self._connection.execute(statement)
        except sqlite3.Error as exc:
            raise RepositoryError("Unable to initialize evidence tables") from exc

    def all_records(self) -> list[EvidenceRecord]:
        rows = self._connection.execute(
            f"SELECT payload FROM {RECORD_TABLE} ORDER BY evidence_id ASC"
        ).fetchall()
        return [EvidenceRecord.from_dict(_decode(row[0])) for row in rows]

    def get_record(self, evidence_id: str) -> EvidenceRecord | None:
        row = self._connection.execute(
            f"SELECT payload FROM {RECORD_TABLE} WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        return EvidenceRecord.from_dict(_decode(row[0])) if row is not None else None

    def save_record(self, record: EvidenceRecord) -> None:
        payload = _encode(record.as_dict())
        try:
            with self._connection:
                self._connection.execute(
                    f"INSERT INTO {RECORD_TABLE} (evidence_id, payload, updated_at) "
                    "VALUES (?, ?, ?) ON CONFLICT(evidence_id) DO UPDATE SET "
                    "payload = excluded.payload, updated_at = excluded.updated_at",
                    (record.id, payload, record.updated_at),
                )
        except sqlite3.Error as exc:
            raise RepositoryError("Unable to save evidence record") from exc

    def delete_record(self, evidence_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM {RECORD_TABLE} WHERE evidence_id = ?", (evidence_id,)
            )
        return cursor.rowcount > 0

    def custody_events(self, evidence_id: str = "") -> list[CustodyEvent]:
        if evidence_id:
            rows = self._connection.execute(
                f"SELECT payload FROM {CUSTODY_TABLE} WHERE evidence_id = ? ORDER BY id ASC",
                (evidence_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                f"SELECT payload FROM {CUSTODY_TABLE} ORDER BY id ASC"
            ).fetchall()
        return [CustodyEvent.from_dict(_decode(row[0])) for row in rows]

    def save_custody_event(self, event: CustodyEvent) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    f"INSERT OR REPLACE INTO {CUSTODY_TABLE} (id, evidence_id, payload) "
                    "VALUES (?, ?, ?)",
                    (event.id, event.evidence_id, _encode(event.as_dict())),
                )
        except sqlite3.Error as exc:
            raise RepositoryError("Unable to save custody event") from exc

    def delete_custody(self, evidence_id: str) -> int:
        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM {CUSTODY_TABLE} WHERE evidence_id = ?", (evidence_id,)
            )
        return cursor.rowcount

    def all_links(self) -> list[FindingLink]:
        rows = self._connection.execute(
            f"SELECT payload FROM {LINK_TABLE} ORDER BY id ASC"
        ).fetchall()
        return [FindingLink.from_dict(_decode(row[0])) for row in rows]

    def save_link(self, link: FindingLink) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    f"INSERT OR REPLACE INTO {LINK_TABLE} (id, evidence_id, payload) "
                    "VALUES (?, ?, ?)",
                    (link.id, link.evidence_id, _encode(link.as_dict())),
                )
        except sqlite3.Error as exc:
            raise RepositoryError("Unable to save finding link") from exc

    def delete_link(self, link_id: int) -> bool:
        with self._connection:
            cursor = self._connection.execute(f"DELETE FROM {LINK_TABLE} WHERE id = ?", (link_id,))
        return cursor.rowcount > 0

    def delete_links(self, evidence_id: str) -> int:
        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM {LINK_TABLE} WHERE evidence_id = ?", (evidence_id,)
            )
        return cursor.rowcount

    def all_policies(self) -> list[RetentionPolicy]:
        rows = self._connection.execute(
            f"SELECT payload FROM {RETENTION_TABLE} ORDER BY evidence_id ASC"
        ).fetchall()
        return [RetentionPolicy.from_dict(_decode(row[0])) for row in rows]

    def save_policy(self, policy: RetentionPolicy) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    f"INSERT OR REPLACE INTO {RETENTION_TABLE} (evidence_id, payload) "
                    "VALUES (?, ?)",
                    (policy.evidence_id, _encode(policy.as_dict())),
                )
        except sqlite3.Error as exc:
            raise RepositoryError("Unable to save retention policy") from exc

    def delete_policy(self, evidence_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM {RETENTION_TABLE} WHERE evidence_id = ?", (evidence_id,)
            )
        return cursor.rowcount > 0

    def all_manifests(self) -> list[EvidenceManifest]:
        rows = self._connection.execute(
            f"SELECT payload FROM {MANIFEST_TABLE} ORDER BY id ASC"
        ).fetchall()
        return [EvidenceManifest.from_dict(_decode(row[0])) for row in rows]

    def save_manifest(self, manifest: EvidenceManifest) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    f"INSERT INTO {MANIFEST_TABLE} (checksum, generated_at, payload) "
                    "VALUES (?, ?, ?)",
                    (manifest.checksum, manifest.generated_at, _encode(manifest.as_dict())),
                )
        except sqlite3.Error as exc:
            raise RepositoryError("Unable to save evidence manifest") from exc


def build_repository(source: Vault | sqlite3.Connection | None = None) -> EvidenceRepository:
    """Return a SQLite repository for a vault, or an in-memory repository."""
    if source is None:
        return InMemoryEvidenceRepository()
    return SQLiteEvidenceRepository(source)


def repository_counts(repository: EvidenceRepository) -> dict[str, int]:
    """Return row counts for each repository section."""
    return {
        "records": len(repository.all_records()),
        "custody": len(repository.custody_events()),
        "links": len(repository.all_links()),
        "policies": len(repository.all_policies()),
        "manifests": len(repository.all_manifests()),
    }
