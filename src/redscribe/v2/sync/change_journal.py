"""Change journal for snapshot comparison and sync planning."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from redscribe.domain.utils import utc_now
from redscribe.storage.db import Vault
from redscribe.v2.sync.checksums import checksum_json
from redscribe.v2.sync.models import ChangeRecord, SnapshotRecord


def record_key(record: Mapping[str, Any]) -> str:
    """Return a stable identity key for a portable note record."""
    path = str(record.get("path", "")).strip()
    if path:
        return f"path:{path}"
    kind = str(record.get("kind", "note"))
    title = str(record.get("title", "")).strip() or "untitled"
    identifier = record.get("id")
    if isinstance(identifier, int) and identifier > 0:
        return f"{kind}:{identifier}:{title.casefold()}"
    return f"{kind}:{title.casefold()}"


def normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a record mapping for comparisons and checksums."""
    payload = {
        "id": int(record.get("id", 0) or 0),
        "parent_id": record.get("parent_id"),
        "title": str(record.get("title", "")),
        "kind": str(record.get("kind", "note")),
        "content": str(record.get("content", "")),
        "tags": str(record.get("tags", "")),
        "target": str(record.get("target", "")),
        "status": str(record.get("status", "todo")),
        "difficulty": str(record.get("difficulty", "")),
        "flag": str(record.get("flag", "")),
        "pinned": bool(record.get("pinned", False)),
        "sort_order": int(record.get("sort_order", 0) or 0),
        "created_at": str(record.get("created_at", "")),
        "updated_at": str(record.get("updated_at", "")),
        "deleted_at": record.get("deleted_at"),
        "path": str(record.get("path", "")),
    }
    payload["checksum"] = str(record.get("checksum") or checksum_json(payload))
    return payload


def snapshot_from_node(vault: Vault, node: Any) -> SnapshotRecord:
    """Build a portable snapshot record from a vault node."""
    path = vault.path_of(node.id, include_self=True)
    payload = normalize_record(
        {
            "id": node.id,
            "parent_id": node.parent_id,
            "title": node.title,
            "kind": node.kind,
            "content": node.content,
            "tags": node.tags,
            "target": node.target,
            "status": node.status,
            "difficulty": node.difficulty,
            "flag": node.flag,
            "pinned": node.pinned,
            "sort_order": node.sort_order,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
            "deleted_at": getattr(node, "deleted_at", None),
            "path": path,
        }
    )
    return SnapshotRecord.from_dict(payload)


@dataclass(slots=True)
class ChangeJournal:
    """Compute, filter, and serialize change sets between snapshots."""

    local_label: str = "local"
    remote_label: str = "remote"
    created_at: str = field(default_factory=utc_now)
    entries: list[ChangeRecord] = field(default_factory=list)

    def capture_vault(
        self,
        vault: Vault,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """Capture the current vault state as normalized records."""
        if include_deleted:
            rows = vault.connection.execute(
                "SELECT * FROM nodes ORDER BY kind DESC, parent_id, sort_order, id"
            ).fetchall()
            nodes = [vault._row_to_node(row) for row in rows]
        else:
            nodes = vault.live_nodes()
        return [snapshot_from_node(vault, node).as_dict() for node in nodes]

    def build(
        self,
        local: Iterable[Mapping[str, Any]],
        remote: Iterable[Mapping[str, Any]],
    ) -> list[ChangeRecord]:
        """Build a change journal comparing local and remote records."""
        local_map = {record_key(item): normalize_record(item) for item in local}
        remote_map = {record_key(item): normalize_record(item) for item in remote}
        self.entries = []
        keys = sorted(set(local_map) | set(remote_map))
        for key in keys:
            left = local_map.get(key)
            right = remote_map.get(key)
            if left is None and right is not None:
                self.entries.append(
                    ChangeRecord(
                        key=key,
                        action="create",
                        entity_type=str(right.get("kind", "note")),
                        title=str(right.get("title", "")),
                        path=str(right.get("path", "")),
                        checksum=str(right.get("checksum", "")),
                        updated_at=str(right.get("updated_at", "")),
                        remote=right,
                    )
                )
                continue
            if right is None and left is not None:
                self.entries.append(
                    ChangeRecord(
                        key=key,
                        action="delete",
                        entity_type=str(left.get("kind", "note")),
                        title=str(left.get("title", "")),
                        path=str(left.get("path", "")),
                        checksum=str(left.get("checksum", "")),
                        updated_at=str(left.get("updated_at", "")),
                        local=left,
                    )
                )
                continue
            if left is None or right is None:
                continue
            if left.get("checksum") == right.get("checksum"):
                self.entries.append(
                    ChangeRecord(
                        key=key,
                        action="unchanged",
                        entity_type=str(left.get("kind", "note")),
                        title=str(left.get("title", "")),
                        path=str(left.get("path", "")),
                        checksum=str(left.get("checksum", "")),
                        updated_at=str(left.get("updated_at", "")),
                        local=left,
                        remote=right,
                    )
                )
            else:
                self.entries.append(
                    ChangeRecord(
                        key=key,
                        action="update",
                        entity_type=str(left.get("kind", "note")),
                        title=str(left.get("title", "") or right.get("title", "")),
                        path=str(left.get("path", "") or right.get("path", "")),
                        checksum=str(right.get("checksum", "")),
                        updated_at=str(right.get("updated_at", "") or left.get("updated_at", "")),
                        local=left,
                        remote=right,
                    )
                )
        return list(self.entries)

    def by_action(self, action: str) -> list[ChangeRecord]:
        return [entry for entry in self.entries if entry.action == action]

    def actionable(self) -> list[ChangeRecord]:
        return [entry for entry in self.entries if entry.action != "unchanged"]

    def summary(self) -> dict[str, int]:
        counts = {"create": 0, "update": 0, "delete": 0, "unchanged": 0}
        for entry in self.entries:
            counts[entry.action] = counts.get(entry.action, 0) + 1
        counts["total"] = len(self.entries)
        counts["actionable"] = len(self.actionable())
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "local_label": self.local_label,
            "remote_label": self.remote_label,
            "summary": self.summary(),
            "entries": [entry.as_dict() for entry in self.entries],
        }


def diff_records(
    local: Iterable[Mapping[str, Any]],
    remote: Iterable[Mapping[str, Any]],
) -> ChangeJournal:
    """Return a populated change journal for two record collections."""
    journal = ChangeJournal()
    journal.build(local, remote)
    return journal
