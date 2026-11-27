"""In-memory persistence adapters for automation runs and schedules.

The store is the only place that owns run identity and ordering. It maintains
secondary indexes for playbook, status and schedule lookups, and can export a
plain-data snapshot that round-trips through the v4 API envelope.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from redscribe.v4.automation_v4.types import (
    PlaybookDag,
    RunRecord,
    RunStatus,
    Schedule,
    text,
)


class StoreError(ValueError):
    """Raised for inconsistent or malformed persisted data."""


@dataclass(frozen=True, slots=True)
class StorageStats:
    """A small, deterministic summary of store contents."""

    runs: int
    schedules: int
    playbooks: int
    terminal_runs: int

    def to_dict(self) -> dict[str, object]:
        return {
            "runs": self.runs,
            "schedules": self.schedules,
            "playbooks": self.playbooks,
            "terminal_runs": self.terminal_runs,
        }


def _sorted_runs(runs: Iterable[RunRecord]) -> tuple[RunRecord, ...]:
    return tuple(sorted(runs, key=lambda run: (run.started_at, run.id)))


class RunStore:
    """Crud store with deterministic indexes and snapshot export."""

    SCHEMA_VERSION = 1

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._schedules: dict[str, Schedule] = {}
        self._dags: dict[str, PlaybookDag] = {}
        self._by_playbook: dict[str, set[str]] = {}
        self._by_status: dict[RunStatus, set[str]] = {}
        self._schedule_index: dict[str, set[str]] = {}

    def put(self, run: RunRecord) -> RunRecord:
        """Insert or replace a run, refreshing secondary indexes."""
        if not run.id:
            raise StoreError("run id must not be empty")
        existing = self._runs.get(run.id)
        if existing is not None:
            self._unindex(existing)
        self._runs[run.id] = run
        self._by_playbook.setdefault(run.playbook_id, set()).add(run.id)
        self._by_status.setdefault(run.status, set()).add(run.id)
        return run

    def _unindex(self, run: RunRecord) -> None:
        playbook_runs = self._by_playbook.get(run.playbook_id)
        if playbook_runs is not None:
            playbook_runs.discard(run.id)
            if not playbook_runs:
                del self._by_playbook[run.playbook_id]
        status_runs = self._by_status.get(run.status)
        if status_runs is not None:
            status_runs.discard(run.id)
            if not status_runs:
                del self._by_status[run.status]

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def require(self, run_id: str) -> RunRecord:
        run = self._runs.get(run_id)
        if run is None:
            raise StoreError(f"unknown run: {run_id}")
        return run

    def delete(self, run_id: str) -> RunRecord:
        """Remove a run and return the deleted snapshot."""
        run = self.require(run_id)
        self._unindex(run)
        del self._runs[run_id]
        return run

    def all_runs(self) -> tuple[RunRecord, ...]:
        return _sorted_runs(self._runs.values())

    def by_playbook(self, playbook_id: str) -> tuple[RunRecord, ...]:
        """Return every run for one playbook in deterministic order."""
        return _sorted_runs(self._runs[run_id] for run_id in self._by_playbook.get(playbook_id, ()))

    def by_status(self, status: RunStatus) -> tuple[RunRecord, ...]:
        return _sorted_runs(self._runs[run_id] for run_id in self._by_status.get(status, ()))

    def history(
        self, playbook_id: str | None = None, status: RunStatus | None = None
    ) -> tuple[RunRecord, ...]:
        """Filter runs by playbook and/or status without losing order."""
        if playbook_id is None and status is None:
            return self.all_runs()
        if playbook_id is not None and status is not None:
            ids = self._by_playbook.get(playbook_id, set()) & self._by_status.get(status, set())
            return _sorted_runs(self._runs[run_id] for run_id in ids)
        if playbook_id is not None:
            return self.by_playbook(playbook_id)
        assert status is not None
        return self.by_status(status)

    def recent(self, limit: int = 10) -> tuple[RunRecord, ...]:
        """Return the newest runs, oldest-first within the returned slice."""
        if limit < 0:
            raise StoreError("limit must be >= 0")
        runs = self.all_runs()
        return runs[-limit:] if limit else ()

    def prune(self, keep: int = 50) -> int:
        """Keep at most ``keep`` runs per playbook, returning the removal count."""
        if keep < 1:
            raise StoreError("keep must be >= 1")
        removed = 0
        for playbook_id in sorted(self._by_playbook):
            runs = self.by_playbook(playbook_id)
            for run in runs[:-keep]:
                self.delete(run.id)
                removed += 1
        return removed

    def put_schedule(self, schedule: Schedule) -> Schedule:
        """Insert or replace a schedule and refresh its playbook index."""
        if not schedule.id:
            raise StoreError("schedule id must not be empty")
        existing = self._schedules.get(schedule.id)
        if existing is not None:
            self._unschedule(existing)
        self._schedules[schedule.id] = schedule
        self._schedule_index.setdefault(schedule.playbook_id, set()).add(schedule.id)
        return schedule

    def _unschedule(self, schedule: Schedule) -> None:
        ids = self._schedule_index.get(schedule.playbook_id)
        if ids is not None:
            ids.discard(schedule.id)
            if not ids:
                del self._schedule_index[schedule.playbook_id]

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        return self._schedules.get(schedule_id)

    def delete_schedule(self, schedule_id: str) -> Schedule:
        schedule = self._schedules.get(schedule_id)
        if schedule is None:
            raise StoreError(f"unknown schedule: {schedule_id}")
        self._unschedule(schedule)
        del self._schedules[schedule_id]
        return schedule

    def schedules_for(self, playbook_id: str) -> tuple[Schedule, ...]:
        ids = self._schedule_index.get(playbook_id, ())
        return tuple(
            sorted(
                (self._schedules[schedule_id] for schedule_id in ids),
                key=lambda item: (item.next_run, item.id),
            )
        )

    def all_schedules(self) -> tuple[Schedule, ...]:
        return tuple(sorted(self._schedules.values(), key=lambda item: (item.id, item.next_run)))

    def stats(self) -> StorageStats:
        return StorageStats(
            runs=len(self._runs),
            schedules=len(self._schedules),
            playbooks=len(self._by_playbook),
            terminal_runs=sum(1 for run in self._runs.values() if run.status.is_terminal),
        )

    def export(self) -> dict[str, object]:
        """Serialize the entire store to plain data for persistence."""
        return {
            "schema_version": self.SCHEMA_VERSION,
            "runs": [run.to_dict() for run in self.all_runs()],
            "schedules": [schedule.to_dict() for schedule in self.all_schedules()],
            "playbooks": [dag.to_dict() for dag in self.all_dags()],
        }

    def import_snapshot(self, payload: Mapping[str, object]) -> tuple[int, int]:
        """Load a snapshot into this store, replacing current contents."""
        version = payload.get("schema_version", self.SCHEMA_VERSION)
        if version != self.SCHEMA_VERSION:
            raise StoreError(f"unsupported schema version: {version}")
        raw_runs = payload.get("runs", [])
        raw_schedules = payload.get("schedules", [])
        raw_dags = payload.get("playbooks", [])
        if not isinstance(raw_runs, list | tuple) or not isinstance(raw_schedules, list | tuple):
            raise StoreError("runs and schedules must be arrays")
        if not isinstance(raw_dags, list | tuple):
            raise StoreError("playbooks must be an array")
        runs: list[RunRecord] = []
        schedules: list[Schedule] = []
        dags: list[PlaybookDag] = []
        for item in raw_runs:
            if not isinstance(item, Mapping):
                raise StoreError("run entries must be objects")
            runs.append(RunRecord.from_dict(item))
        for item in raw_schedules:
            if not isinstance(item, Mapping):
                raise StoreError("schedule entries must be objects")
            schedules.append(Schedule.from_dict(item))
        if len({run.id for run in runs}) != len(runs):
            raise StoreError("duplicate run id in snapshot")
        if len({schedule.id for schedule in schedules}) != len(schedules):
            raise StoreError("duplicate schedule id in snapshot")
        for item in raw_dags:
            if not isinstance(item, Mapping):
                raise StoreError("playbook entries must be objects")
            dags.append(PlaybookDag.from_dict(item))
        if len({dag.id for dag in dags}) != len(dags):
            raise StoreError("duplicate playbook id in snapshot")
        self.clear()
        for dag in dags:
            self.put_dag(dag)
        for run in runs:
            self.put(run)
        for schedule in schedules:
            self.put_schedule(schedule)
        return len(runs), len(schedules)

    def clear(self) -> None:
        """Drop all runs and schedules, leaving indexes empty."""
        self._runs.clear()
        self._schedules.clear()
        self._dags.clear()
        self._by_playbook.clear()
        self._by_status.clear()
        self._schedule_index.clear()

    def put_dag(self, dag: PlaybookDag) -> PlaybookDag:
        """Store a playbook definition by id."""
        if not dag.id:
            raise StoreError("playbook id must not be empty")
        self._dags[dag.id] = dag
        return dag

    def get_dag(self, playbook_id: str) -> PlaybookDag | None:
        return self._dags.get(playbook_id)

    def require_dag(self, playbook_id: str) -> PlaybookDag:
        dag = self._dags.get(playbook_id)
        if dag is None:
            raise StoreError(f"unknown playbook: {playbook_id}")
        return dag

    def all_dags(self) -> tuple[PlaybookDag, ...]:
        return tuple(sorted(self._dags.values(), key=lambda item: (item.name, item.id)))

    def describe(self) -> str:
        """Short human-readable store summary."""
        stats = self.stats()
        return f"runs={stats.runs} schedules={stats.schedules} playbooks={stats.playbooks}"

    @staticmethod
    def summary_text(value: object) -> str:
        """Decode an optional textual field from external payloads."""
        return text(value)
