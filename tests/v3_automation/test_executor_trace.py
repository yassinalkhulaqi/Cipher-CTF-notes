"""Mutation sinks, step execution, traces and field-level diffs."""

from __future__ import annotations

from dataclasses import replace

import pytest

from redscribe.v3.automation.encoding import canonical_json, digest, flatten, redact_value
from redscribe.v3.automation.errors import (
    DryRunWriteAttemptedError,
    UnsupportedStepError,
    VariableResolutionError,
)
from redscribe.v3.automation.executor import (
    InMemoryMutationSink,
    StepExecutor,
    TraceOnlySink,
    build_intent,
)
from redscribe.v3.automation.parsing import parse_playbook
from redscribe.v3.automation.trace import TraceRecorder, diff_runs, diff_traces, timeline
from redscribe.v3.automation.types import (
    ConditionOperator,
    MutationIntent,
    PlaybookDefinition,
    RunMode,
    RunRecord,
    RunStatus,
    StepCondition,
    StepDefinition,
    StepKind,
    StepStatus,
)
from redscribe.v3.automation.variables import validate_values

from .helpers import playbook_payload, sample_playbook


def _intent(kind: StepKind = StepKind.CREATE_NOTE, key: str = "k1") -> MutationIntent:
    return MutationIntent(
        step_id="s1",
        kind=kind,
        target="note:auto_s1_item",
        payload={"title": "Item"},
        key=key,
        inverse={"action": "delete", "ref": "note:auto_s1_item"},
    )


def test_canonical_helpers_are_deterministic() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert digest({"a": 1}) == digest({"a": 1})
    assert flatten({"a": {"b": [1, {"c": 2}]}}) == {"a.b[0]": 1, "a.b[1].c": 2}
    assert redact_value(
        {"token": "x", "nested": {"password": "y"}}, secrets=frozenset({"token", "password"})
    ) == {
        "token": "***",
        "nested": {"password": "***"},
    }


def test_build_intent_is_deterministic_and_data_only() -> None:
    step = StepDefinition(id="collect", title="Collect", kind=StepKind.CREATE_NOTE)
    first = build_intent(step, {"title": "Recon notes"}, playbook_ref="playbook:p")
    second = build_intent(step, {"title": "Recon notes"}, playbook_ref="playbook:p")
    assert first == second
    assert first.kind is StepKind.CREATE_NOTE
    assert first.target.startswith("note:auto_collect_")
    assert first.payload["playbook_ref"] == "playbook:p"
    assert first.inverse["action"] == "delete"
    link = build_intent(
        StepDefinition(id="link", title="Link", kind=StepKind.ATTACH_EVIDENCE),
        {"evidence_ref": "evidence:a", "target_ref": "finding:b", "link_kind": "evidences"},
        playbook_ref="playbook:p",
    )
    assert link.kind is StepKind.ATTACH_EVIDENCE
    assert link.payload["target_ref"] == "finding:b"
    assert link.inverse["action"] == "unlink"


def test_build_intent_rejects_invalid_entity_refs() -> None:
    with pytest.raises(VariableResolutionError):
        build_intent(
            StepDefinition(id="link", title="Link", kind=StepKind.ATTACH_EVIDENCE),
            {"evidence_ref": "garbage"},
            playbook_ref="playbook:p",
        )


def test_in_memory_sink_preview_commit_and_idempotency() -> None:
    sink = InMemoryMutationSink()
    intent = _intent()
    preview = sink.preview(intent)
    assert preview.applied is False
    assert sink.snapshot()["collections"]["notes"] == {}
    first = sink.commit(intent)
    second = sink.commit(intent)
    assert first.applied is True
    assert second.applied is False
    assert sink.snapshot()["collections"]["notes"][intent.target]["title"] == "Item"
    assert len(sink.snapshot()["applied"]) == 1
    assert sink.entity_digest() != InMemoryMutationSink().entity_digest()


def test_in_memory_sink_compensates_and_reports_coverage() -> None:
    sink = InMemoryMutationSink()
    note = _intent()
    event = _intent(StepKind.EMIT_EVENT, "k2")
    for intent in (note, event):
        sink.commit(intent)
    before = sink.entity_digest()
    assert sink.compensation_coverage((note, event)) == (event.key,)
    assert sink.compensate(note).applied is True
    assert sink.compensate(event).applied is True
    assert sink.compensate(note).applied is False
    assert sink.entity_digest() != before
    assert sink.snapshot()["collections"]["notes"] == {}
    assert sink.compensation_coverage((note, event)) == ()


def test_sink_rejects_unknown_kinds() -> None:
    fake = replace(_intent(), kind="execute")
    sink = InMemoryMutationSink()
    with pytest.raises(UnsupportedStepError):
        sink.commit(fake)


def test_trace_only_sink_never_writes() -> None:
    sink = TraceOnlySink()
    intent = _intent()
    assert sink.preview(intent).applied is False
    assert sink.preview(intent).applied is False
    assert sink.snapshot() == {"writes": 0, "previews": 2}
    assert sink.entity_digest() == TraceOnlySink().entity_digest()
    with pytest.raises(DryRunWriteAttemptedError):
        sink.commit(intent)
    with pytest.raises(DryRunWriteAttemptedError):
        sink.compensate(intent)


def test_step_executor_plans_and_executes_steps() -> None:
    playbook = sample_playbook()
    resolution = validate_values(playbook, {"target": "target:t1"})
    executor = StepExecutor(TraceOnlySink())
    planned = executor.execute(
        playbook.step("note"),
        playbook_ref=playbook.ref,
        resolution=resolution,
        outputs={},
        run_id="run_test",
        commit=False,
    )
    assert planned.status is StepStatus.PLANNED
    assert planned.result is not None
    assert planned.result.applied is False
    assert "target:t1" in planned.result.intent.payload["title"]

    live = StepExecutor(InMemoryMutationSink())
    applied = live.execute(
        playbook.step("note"),
        playbook_ref=playbook.ref,
        resolution=resolution,
        outputs={},
        run_id="run_test",
        commit=True,
    )
    assert applied.status is StepStatus.EXECUTED
    assert applied.result is not None
    assert applied.result.applied is True


def test_step_guard_skips_step() -> None:
    step = StepDefinition(
        id="guarded",
        title="Guarded",
        condition=StepCondition(field="vars.flag", operator=ConditionOperator.EQ, value=True),
    )
    playbook = PlaybookDefinition(id="g", title="G", steps=(step,))
    resolution = validate_values(playbook, {})
    outcome = StepExecutor(TraceOnlySink()).execute(
        step,
        playbook_ref=playbook.ref,
        resolution=resolution,
        outputs={},
        run_id="r",
        commit=False,
    )
    assert outcome.status is StepStatus.SKIPPED
    assert outcome.result is None
    assert "Skipped" in outcome.message


def test_trace_recorder_hash_chain_and_timeline() -> None:
    playbook = parse_playbook(playbook_payload())
    recorder = TraceRecorder()
    sink = InMemoryMutationSink()
    executor = StepExecutor(sink)
    resolution = validate_values(playbook, {"target": "target:t1"})
    outputs: dict[str, object] = {}
    for step_id in ("note", "finding"):
        step = playbook.step(step_id)
        outcome = executor.execute(
            step,
            playbook_ref=playbook.ref,
            resolution=resolution,
            outputs=outputs,
            run_id="r",
            commit=True,
        )
        assert outcome.result is not None
        outputs[step.id] = {"ref": outcome.result.ref}
        recorder.record(step, outcome, variables={"target": "target:t1"})
    trace = recorder.finish(
        playbook_ref=playbook.ref,
        mode=RunMode.LIVE,
        variables={"target": "target:t1"},
        input_fingerprint="fp",
        state_digest=sink.entity_digest(),
    )
    assert len(trace.entries) == 2
    assert trace.writes == 2
    assert trace.entries[0].chain != trace.entries[1].chain
    assert trace.digest == trace.entries[-1].chain
    assert len(trace.mutations) == 2
    items = timeline(trace)
    assert [item["step_id"] for item in items] == ["note", "finding"]
    assert items[0]["tone"] == "good"
    assert items[0]["target"].startswith("note:")
    assert trace.as_dict()["mode"] == "live"


def test_diff_traces_and_runs() -> None:
    first = parse_playbook(playbook_payload())
    recorder = TraceRecorder()
    resolution = validate_values(first, {"target": "target:t1"})
    sink = InMemoryMutationSink()
    executor = StepExecutor(sink)
    step = first.step("note")
    outcome = executor.execute(
        step,
        playbook_ref=first.ref,
        resolution=resolution,
        outputs={},
        run_id="r",
        commit=True,
    )
    recorder.record(step, outcome)
    trace_a = recorder.finish(
        playbook_ref=first.ref,
        mode=RunMode.LIVE,
        variables={},
        input_fingerprint="fp1",
        state_digest="sa",
    )
    other = parse_playbook(playbook_payload(title="Changed"))
    recorder2 = TraceRecorder()
    outcome2 = executor.execute(
        other.step("note"),
        playbook_ref=other.ref,
        resolution=validate_values(other, {"target": "target:t2"}),
        outputs={},
        run_id="r",
        commit=True,
    )
    recorder2.record(other.step("note"), outcome2)
    trace_b = recorder2.finish(
        playbook_ref=other.ref,
        mode=RunMode.LIVE,
        variables={},
        input_fingerprint="fp2",
        state_digest="sb",
    )
    differences = diff_traces(trace_a, trace_b)
    assert any(item.path == "input_fingerprint" for item in differences)
    assert any("steps.note[0]" in item.path for item in differences)
    assert all(item.as_dict()["path"] for item in differences)

    run_a = RunRecord(
        id="a", playbook_ref=first.ref, status=RunStatus.COMPLETED, mode=RunMode.LIVE, started_at=1
    )
    run_b = RunRecord(
        id="b",
        playbook_ref=first.ref,
        status=RunStatus.ROLLED_BACK,
        mode=RunMode.LIVE,
        started_at=2,
    )
    run_diffs = diff_runs(run_a, run_b)
    assert any(item.path == "status" for item in run_diffs)
