"""In-memory state tracking for sync operations and conflict sessions."""

from __future__ import annotations

import contextlib
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from redscribe.v2.sync.errors import NotFoundError, ValidationError
from redscribe.v2.sync.models import ConflictRecord


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ConflictSession:
    """A stored set of conflicts awaiting user decisions."""

    session_id: str
    operation: str
    created_at: str
    conflicts: list[ConflictRecord]
    metadata: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "operation": self.operation,
            "created_at": self.created_at,
            "resolved": self.resolved,
            "conflicts": [item.as_dict() for item in self.conflicts],
            "metadata": dict(self.metadata),
            "summary": {
                "total": len(self.conflicts),
                "unresolved": sum(1 for item in self.conflicts if item.resolution == "unresolved"),
            },
        }


@dataclass(slots=True)
class OperationRecord:
    """A tracked sync operation with progress snapshots."""

    operation_id: str
    kind: str
    status: str
    created_at: str
    updated_at: str
    details: dict[str, Any] = field(default_factory=dict)
    progress: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "details": dict(self.details),
            "progress": list(self.progress),
        }


class SyncStateStore:
    """Thread-safe in-memory store for sync sessions and progress."""

    def __init__(self, *, max_operations: int = 200, max_sessions: int = 100) -> None:
        self._lock = Lock()
        self._operations: deque[OperationRecord] = deque(maxlen=max_operations)
        self._sessions: dict[str, ConflictSession] = {}
        self._session_order: deque[str] = deque(maxlen=max_sessions)
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        with self._lock:
            self._counter += 1
            return f"{prefix}-{self._counter:06d}"

    def create_operation(
        self, kind: str, *, details: dict[str, Any] | None = None
    ) -> OperationRecord:
        operation_id = self._next_id("op")
        stamp = _now()
        record = OperationRecord(
            operation_id=operation_id,
            kind=kind,
            status="running",
            created_at=stamp,
            updated_at=stamp,
            details=dict(details or {}),
        )
        with self._lock:
            self._operations.append(record)
        return record

    def update_operation(
        self,
        operation_id: str,
        *,
        status: str | None = None,
        details: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
    ) -> OperationRecord:
        with self._lock:
            record = self._find_operation(operation_id)
            if status is not None:
                record.status = status
            if details:
                record.details.update(details)
            if progress is not None:
                record.progress.append(dict(progress))
            record.updated_at = _now()
            return record

    def complete_operation(
        self, operation_id: str, *, details: dict[str, Any] | None = None
    ) -> OperationRecord:
        return self.update_operation(operation_id, status="completed", details=details)

    def fail_operation(self, operation_id: str, message: str) -> OperationRecord:
        return self.update_operation(
            operation_id,
            status="failed",
            details={"error": message},
        )

    def list_operations(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._operations)[-max(1, limit) :]
            return [item.as_dict() for item in reversed(items)]

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            return self._find_operation(operation_id).as_dict()

    def _find_operation(self, operation_id: str) -> OperationRecord:
        for record in reversed(self._operations):
            if record.operation_id == operation_id:
                return record
        raise NotFoundError(f"Unknown sync operation: {operation_id}")

    def create_conflict_session(
        self,
        operation: str,
        conflicts: Iterable[ConflictRecord],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ConflictSession:
        session_id = self._next_id("conflict")
        session = ConflictSession(
            session_id=session_id,
            operation=operation,
            created_at=_now(),
            conflicts=list(conflicts),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            maxlen = self._session_order.maxlen
            if maxlen is not None and len(self._sessions) >= maxlen:
                oldest = self._session_order[0] if self._session_order else None
                if oldest:
                    self._sessions.pop(oldest, None)
            self._sessions[session_id] = session
            self._session_order.append(session_id)
        return session

    def get_conflict_session(self, session_id: str) -> ConflictSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Unknown conflict session: {session_id}")
        return session

    def list_conflict_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._session_order)[-max(1, limit) :]
            sessions = [self._sessions[item] for item in reversed(ids) if item in self._sessions]
            return [item.as_dict() for item in sessions]

    def resolve_conflict_session(
        self,
        session_id: str,
        resolutions: dict[str, str],
    ) -> ConflictSession:
        if not isinstance(resolutions, dict):
            raise ValidationError("resolutions must be an object")
        session = self.get_conflict_session(session_id)
        for conflict in session.conflicts:
            choice = resolutions.get(conflict.key)
            if choice:
                conflict.resolution = choice
        session.resolved = all(item.resolution != "unresolved" for item in session.conflicts)
        return session

    def discard_conflict_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                raise NotFoundError(f"Unknown conflict session: {session_id}")
            with contextlib.suppress(ValueError):
                self._session_order.remove(session_id)
            return session.as_dict()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            operations = list(self._operations)
            sessions = list(self._sessions.values())
        return {
            "operations": len(operations),
            "operations_running": sum(1 for item in operations if item.status == "running"),
            "operations_failed": sum(1 for item in operations if item.status == "failed"),
            "conflict_sessions": len(sessions),
            "conflicts_unresolved": sum(
                1
                for session in sessions
                for conflict in session.conflicts
                if conflict.resolution == "unresolved"
            ),
        }
