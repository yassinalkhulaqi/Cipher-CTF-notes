"""Run persistence backed by the schema-v5 ``v3_run_records`` table."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from typing import Any, Protocol

from redscribe.v3.automation.encoding import canonical_json, copy_value
from redscribe.v3.automation.errors import RunNotFoundError
from redscribe.v3.automation.types import (
    MutationIntent,
    MutationResult,
    RunMode,
    RunRecord,
    RunStatus,
    StepKind,
    StepStatus,
    TraceEntry,
)


def _encode_entries(entries: tuple[TraceEntry, ...]) -> str:
    """Serialize a trace to a stable JSON string."""
    return canonical_json([entry.as_dict() for entry in entries])


def _decode_entries(raw: str) -> tuple[TraceEntry, ...]:
    """Deserialize a trace from stored JSON."""
    payload = json.loads(raw or "[]")
    return tuple(_entry_from_dict(item) for item in payload)


def _entry_from_dict(payload: dict[str, Any]) -> TraceEntry:
    """Rebuild one trace entry from a stored mapping."""
    result_payload = payload.get("result")
    result: MutationResult | None = None
    if result_payload:
        intent_payload = result_payload["intent"]
        intent = MutationIntent(
            step_id=intent_payload["step_id"],
            kind=StepKind(intent_payload["kind"]),
            target=intent_payload["target"],
            payload=dict(intent_payload.get("payload", {})),
            key=intent_payload["key"],
            inverse=dict(intent_payload.get("inverse", {})),
        )
        result = MutationResult(
            intent=intent,
            ref=result_payload["ref"],
            applied=bool(result_payload["applied"]),
            before=result_payload.get("before"),
            after=result_payload.get("after"),
        )
    return TraceEntry(
        index=int(payload["index"]),
        step_id=payload["step_id"],
        status=StepStatus(payload["status"]),
        kind=StepKind(payload["kind"]),
        message=payload["message"],
        variables=dict(payload.get("variables", {})),
        result=result,
        chain=payload.get("chain", ""),
    )


class RunRecordStore(Protocol):
    """Storage contract for run records."""

    def save(self, record: RunRecord) -> None:
        """Insert or replace a run record."""
        ...

    def get(self, run_id: str) -> RunRecord | None:
        """Look up a record by id."""
        ...

    def list(self, *, playbook_ref: str | None = None, limit: int = 100) -> tuple[RunRecord, ...]:
        """Return records in descending start-time order."""
        ...


class InMemoryRunStore:
    """Non-persistent store used by tests and single-session services."""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}

    def save(self, record: RunRecord) -> None:
        """Store a detached copy of a record."""
        self._records[record.id] = _clone(record)

    def get(self, run_id: str) -> RunRecord | None:
        """Look up a record by id."""
        record = self._records.get(run_id)
        return _clone(record) if record else None

    def list(self, *, playbook_ref: str | None = None, limit: int = 100) -> tuple[RunRecord, ...]:
        """Return records newest first."""
        records = [
            record
            for record in self._records.values()
            if playbook_ref is None or record.playbook_ref == playbook_ref
        ]
        records.sort(key=lambda record: (-record.started_at, record.id))
        return tuple(_clone(record) for record in records[: max(0, limit)])

    def count(self) -> int:
        """Return the number of stored records."""
        return len(self._records)

    def clear(self) -> None:
        """Drop all records."""
        self._records.clear()


def _clone(record: RunRecord) -> RunRecord:
    """Return a detached copy of an immutable run record."""
    return replace(record, variables=copy_value(record.variables))


class SqliteRunStore:
    """SQLite implementation using the append-only schema-v5 table definition."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def ensure_table(self) -> None:
        """Create the run table from the B00 migration step when missing."""
        from redscribe.v3.migrations.v5 import TABLE_STEPS

        step = next(item for item in TABLE_STEPS if item.name == "create_run_records")
        self._connection.execute(step.sql)
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_v3_runs_started ON v3_run_records (started_at);"
        )
        self._connection.commit()

    def save(self, record: RunRecord) -> None:
        """Upsert one run record."""
        self.ensure_table()
        self._connection.execute(
            "INSERT INTO v3_run_records "
            "(id, playbook_ref, status, mode, started_at, finished_at, trace) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, mode=excluded.mode, finished_at=excluded.finished_at, "
            "trace=excluded.trace",
            (
                record.id,
                record.playbook_ref,
                record.status.value,
                record.mode.value,
                record.started_at,
                record.finished_at,
                _encode_entries(record.trace),
            ),
        )
        self._connection.commit()

    def get(self, run_id: str) -> RunRecord | None:
        """Read one run record by id."""
        self.ensure_table()
        row = self._connection.execute(
            "SELECT id, playbook_ref, status, mode, started_at, finished_at, trace "
            "FROM v3_run_records WHERE id = ?",
            (run_id,),
        ).fetchone()
        return _record_from_row(row) if row else None

    def list(self, *, playbook_ref: str | None = None, limit: int = 100) -> tuple[RunRecord, ...]:
        """Read run records newest first."""
        self.ensure_table()
        query = (
            "SELECT id, playbook_ref, status, mode, started_at, finished_at, trace "
            "FROM v3_run_records"
        )
        parameters: list[Any] = []
        if playbook_ref is not None:
            query += " WHERE playbook_ref = ?"
            parameters.append(playbook_ref)
        query += " ORDER BY started_at DESC, id ASC LIMIT ?"
        parameters.append(max(0, limit))
        rows = self._connection.execute(query, parameters).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def count(self) -> int:
        """Count persisted run records."""
        self.ensure_table()
        row = self._connection.execute("SELECT COUNT(*) FROM v3_run_records").fetchone()
        return int(row[0])


def _record_from_row(row: Any) -> RunRecord:
    """Rebuild a run record from a SQLite row."""
    return RunRecord(
        id=row[0],
        playbook_ref=row[1],
        status=RunStatus(row[2]),
        mode=RunMode(row[3]),
        started_at=row[4],
        finished_at=row[5],
        trace=_decode_entries(row[6]),
    )


class RunService:
    """Lifecycle helpers that keep persistence consistent across branches."""

    def __init__(self, store: RunRecordStore) -> None:
        self.store = store

    def begin(self, record: RunRecord) -> RunRecord:
        """Persist a planned run."""
        planned = replace(record, status=RunStatus.PLANNED, finished_at=0.0)
        self.store.save(planned)
        return planned

    def finish(
        self,
        record: RunRecord,
        *,
        trace: tuple[TraceEntry, ...],
        digest: str,
        state_digest: str,
        finished_at: float,
        status: RunStatus = RunStatus.COMPLETED,
    ) -> RunRecord:
        """Persist the terminal state of a run."""
        completed = replace(
            record,
            status=status,
            finished_at=finished_at,
            trace=trace,
            trace_digest=digest,
            state_digest=state_digest,
        )
        self.store.save(completed)
        return completed

    def fail(self, record: RunRecord, *, finished_at: float) -> RunRecord:
        """Persist a failed run."""
        failed = replace(record, status=RunStatus.FAILED, finished_at=finished_at)
        self.store.save(failed)
        return failed

    def get(self, run_id: str) -> RunRecord:
        """Load a record or raise :class:`RunNotFoundError`."""
        record = self.store.get(run_id)
        if record is None:
            raise RunNotFoundError(f"Unknown run: {run_id}", path="run_id")
        return record

    def list(self, *, playbook_ref: str | None = None, limit: int = 100) -> tuple[RunRecord, ...]:
        """List persisted runs."""
        return self.store.list(playbook_ref=playbook_ref, limit=limit)
