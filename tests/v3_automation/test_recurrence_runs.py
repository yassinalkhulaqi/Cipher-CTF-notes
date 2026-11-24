"""Recurrence expansion and persistence in the v3_run_records table."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from redscribe.v3.automation.errors import RecurrenceError
from redscribe.v3.automation.parsing import parse_recurrence
from redscribe.v3.automation.recurrence import (
    humanize,
    next_occurrence,
    occurrences,
    schedule_label,
    validate_recurrence,
)
from redscribe.v3.automation.runs import (
    InMemoryRunStore,
    RunService,
    SqliteRunStore,
    _decode_entries,
    _encode_entries,
)
from redscribe.v3.automation.types import (
    Frequency,
    RecurrenceRule,
    RunMode,
    RunRecord,
    RunStatus,
    StepKind,
    StepStatus,
    TraceEntry,
)

_DAY = 86_400


def _windows(rule: RecurrenceRule, start: float = 0.0) -> tuple[float, ...]:
    return occurrences(rule, start, start + 40 * _DAY, limit=50)


def test_daily_rule_expansion_is_deterministic() -> None:
    rule = RecurrenceRule(frequency=Frequency.DAILY, hour=9, minute=30, start_at=0.0)
    first = _windows(rule)
    assert first == _windows(rule)
    assert len(first) == 40
    assert first[0] < first[1]
    assert schedule_label(first[0]).startswith("1970-01-01")
    assert "09:30 UTC" in humanize(rule)
    assert next_occurrence(rule, first[0]) == first[1]


def test_interval_and_count_are_honored() -> None:
    rule = RecurrenceRule(frequency=Frequency.DAILY, interval=3, count=4)
    found = occurrences(rule, 0.0, 100 * _DAY, limit=20)
    assert len(found) == 4
    assert round((found[1] - found[0]) / _DAY) == 3
    assert occurrences(rule, 0.0, 100 * _DAY, limit=2) == found[:2]
    assert occurrences(rule, 0.0, 0.0) == ()
    assert occurrences(rule, 10.0, 5.0) == ()
    with pytest.raises(RecurrenceError):
        occurrences(rule, 0.0, 10 * _DAY, limit=-1)


def test_weekly_rule_expands_selected_days() -> None:
    rule = RecurrenceRule(frequency=Frequency.WEEKLY, by_weekday=(0, 2), hour=6, start_at=2 * _DAY)
    found = _windows(rule, 2 * _DAY)
    assert len(found) >= 10
    from datetime import datetime, timezone

    weekdays = {datetime.fromtimestamp(value, tz=timezone.utc).weekday() for value in found[:6]}
    assert weekdays == {0, 2}
    assert "Mon" in humanize(rule)
    assert any(
        issue.code == "missing_weekday"
        for issue in validate_recurrence(RecurrenceRule(frequency=Frequency.WEEKLY))
    )


def test_monthly_rule_clamps_short_months() -> None:
    from datetime import datetime, timezone

    rule = RecurrenceRule(frequency=Frequency.MONTHLY, by_month_day=31, hour=12, start_at=0.0)
    found = occurrences(rule, 0.0, 200 * _DAY, limit=12)
    assert len(found) == 6
    for timestamp in found:
        moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        assert moment.hour == 12
        assert moment.day in (28, 30, 31)
    assert "day 31" in humanize(rule)


def test_hourly_rule_and_end_boundary() -> None:
    rule = parse_recurrence({"frequency": "hourly", "interval": 2, "minute": 15})
    found = occurrences(rule, 0.0, 10 * 3600, limit=10)
    assert len(found) == 5
    assert round(found[1] - found[0]) == 7200
    bounded = parse_recurrence({"frequency": "daily", "start_at": 0.0, "end_at": 3 * _DAY})
    assert len(occurrences(bounded, 0.0, 100 * _DAY)) == 3
    invalid = SimpleNamespace(
        frequency=Frequency.DAILY,
        by_weekday=(),
        by_month_day=None,
        start_at=10.0,
        end_at=1.0,
    )
    assert any(issue.code == "invalid_window" for issue in validate_recurrence(invalid))


def _record(run_id: str, timestamp: float) -> RunRecord:
    return RunRecord(
        id=run_id,
        playbook_ref="playbook:p",
        status=RunStatus.COMPLETED,
        mode=RunMode.LIVE,
        started_at=timestamp,
        trace=(
            TraceEntry(
                index=0,
                step_id="s1",
                status=StepStatus.EXECUTED,
                kind=StepKind.CREATE_NOTE,
                message="done",
            ),
        ),
    )


def test_in_memory_run_store_orders_and_filters() -> None:
    store = InMemoryRunStore()
    store.save(_record("b", 2.0))
    store.save(_record("a", 1.0))
    store.save(_record("c", 3.0))
    assert [record.id for record in store.list()] == ["c", "b", "a"]
    assert [record.id for record in store.list(limit=2)] == ["c", "b"]
    assert store.count() == 3
    first = store.get("a")
    assert first is not None
    assert first.trace[0].message == "done"
    copy = store.get("a")
    assert copy is not None
    assert copy is not first
    store.clear()
    assert store.count() == 0
    assert store.get("a") is None


def test_run_service_lifecycle() -> None:
    service = RunService(InMemoryRunStore())
    record = RunRecord(
        id="run-1",
        playbook_ref="playbook:p",
        status=RunStatus.PLANNED,
        mode=RunMode.LIVE,
        started_at=1.0,
    )
    assert service.begin(record).status is RunStatus.PLANNED
    finished = service.finish(
        record, trace=record.trace, digest="abc", state_digest="def", finished_at=2.0
    )
    assert finished.status is RunStatus.COMPLETED
    assert finished.trace_digest == "abc"
    assert service.get("run-1").finished_at == 2.0
    failed = service.fail(record, finished_at=3.0)
    assert failed.status is RunStatus.FAILED
    from redscribe.v3.automation.errors import RunNotFoundError

    with pytest.raises(RunNotFoundError):
        service.get("missing")


def test_trace_json_round_trip_preserves_intents() -> None:
    from redscribe.v3.automation.executor import build_intent
    from redscribe.v3.automation.types import MutationResult, StepDefinition, StepKind

    intent = build_intent(
        StepDefinition(id="s", title="S", kind=StepKind.CREATE_NOTE),
        {"title": "Title"},
        playbook_ref="playbook:p",
    )
    entry = TraceEntry(
        index=0,
        step_id="s",
        status=StepStatus.EXECUTED,
        kind=StepKind.CREATE_NOTE,
        message="done",
        result=MutationResult(intent=intent, ref=intent.target, applied=True),
        chain="chain",
    )
    restored = _decode_entries(_encode_entries((entry,)))
    assert restored == (entry,)
    assert restored[0].result is not None
    assert restored[0].result.intent.key == intent.key


def test_sqlite_run_store_uses_schema_v5_table() -> None:
    connection = sqlite3.connect(":memory:")
    store = SqliteRunStore(connection)
    store.ensure_table()
    record = _record("sqlite-1", 5.0)
    store.save(record)
    assert store.count() == 1
    loaded = store.get("sqlite-1")
    assert loaded is not None
    assert loaded.status is RunStatus.COMPLETED
    assert len(loaded.trace) == 1
    assert [item.id for item in store.list(playbook_ref="playbook:p")] == ["sqlite-1"]
    assert store.list(playbook_ref="other") == ()
    updated = replace(record, status=RunStatus.ROLLED_BACK)
    store.save(updated)
    assert store.get("sqlite-1").status is RunStatus.ROLLED_BACK
    connection.close()
