"""Tests for the recent/frequent usage model."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.commands.types import CommandInvocation
from redscribe.v3.commands.usage import UsageEvent, UsageModel


def test_usage_records_and_stats() -> None:
    model = UsageModel()
    invocation = CommandInvocation("view.split")
    event = model.record(invocation, pane_id="pane:main", now=10.0)
    assert event.command_id == "view.split"
    assert event.pane_id == "pane:main"
    stats = model.stats("view.split")
    assert stats.count == 1
    assert stats.first_timestamp == 10.0
    assert stats.span == 0.0
    assert model.size() == 1
    assert model.stats("never.used").count == 0


def test_usage_recent_is_deduplicated() -> None:
    model = UsageModel()
    for command_id, timestamp in (("a.one", 1.0), ("b.two", 2.0), ("a.one", 3.0)):
        model.record(CommandInvocation(command_id), now=timestamp)
    recent = model.recent(5)
    assert [event.command_id for event in recent] == ["a.one", "b.two"]
    assert recent[0].timestamp == 3.0
    assert len(model.recent(1)) == 1


def test_usage_frequent_ordering() -> None:
    model = UsageModel()
    for _ in range(3):
        model.record(CommandInvocation("a.one"), now=1.0)
    for _ in range(5):
        model.record(CommandInvocation("b.two"), now=2.0)
    model.record(CommandInvocation("c.three"), now=3.0)
    assert model.frequent(3) == (("b.two", 5), ("a.one", 3), ("c.three", 1))


def test_usage_decay_with_fixed_clock() -> None:
    clock = FixedClock(start=100.0)
    model = UsageModel(half_life_seconds=100.0, clock=clock)
    model.record(CommandInvocation("view.open"), now=0.0)
    assert model.recency_score("view.open", 0.0) == 1.0
    assert model.recency_score("view.open", 100.0) == pytest.approx(0.5)
    assert model.recency_score("view.open", 200.0) == pytest.approx(0.25)
    assert model.frequency_score("view.open") > 0
    assert model.score("view.open", 100.0) == pytest.approx(
        0.6 * 0.5 + 0.4 * model.frequency_score("view.open")
    )
    assert model.score("unknown.command", 100.0) == 0.0


def test_usage_snapshot_roundtrip_and_prune() -> None:
    model = UsageModel()
    model.record(CommandInvocation("a.one"), now=1.0)
    model.record(CommandInvocation("b.two"), now=9.0)
    snapshot = model.snapshot()
    assert snapshot["half_life_seconds"] == 86400.0
    assert len(snapshot["events"]) == 2
    restored = UsageModel()
    restored.load(snapshot)
    assert restored.size() == 2
    assert restored.stats("a.one").count == 1
    assert restored.prune(5.0) == 1
    assert restored.stats("a.one").count == 0
    restored.clear()
    assert restored.size() == 0


def test_usage_validation_errors() -> None:
    with pytest.raises(ValueError):
        UsageModel(half_life_seconds=0)
    with pytest.raises(ValueError):
        UsageEvent(command_id="", timestamp=0)
    with pytest.raises(ValueError):
        UsageEvent(command_id="a.b", timestamp=-1)
    model = UsageModel()
    with pytest.raises(ValueError):
        model.recent(0)
    with pytest.raises(ValueError):
        model.frequent(0)
    with pytest.raises(ValueError):
        model.load({"events": "bad"})
    with pytest.raises(ValueError):
        model.load({"events": ["bad"]})


def test_usage_model_uses_injected_clock() -> None:
    clock = FixedClock(start=50.0, step=10.0)
    model = UsageModel(clock=clock)
    first = model.record(CommandInvocation("a.one"))
    second = model.record(CommandInvocation("a.one"))
    assert (first.timestamp, second.timestamp) == (50.0, 60.0)
    assert clock.now_timestamp() == 70.0
