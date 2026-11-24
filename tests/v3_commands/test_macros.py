"""Tests for data-only macro recording, storage, and expansion."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.commands.macros import (
    MAX_MACRO_STEPS,
    Macro,
    MacroError,
    MacroLibrary,
    MacroRecorder,
    MacroStep,
    expand_macro,
    macro_steps_as_data,
)
from redscribe.v3.commands.types import CommandInvocation


def test_macro_step_validation_and_dict() -> None:
    step = MacroStep("view.split", {"orientation": "vertical"}, note="split")
    payload = step.as_dict()
    assert payload["context_mode"] == "inherit"
    assert payload["note"] == "split"
    with pytest.raises(MacroError):
        MacroStep("")
    with pytest.raises(MacroError):
        MacroStep("x.y", context_mode="shell")
    with pytest.raises(MacroError):
        MacroStep("x.y", {"a": 1})  # type: ignore[dict-item]


def test_macro_requires_steps() -> None:
    with pytest.raises(MacroError):
        Macro(id="m1", name="Empty", steps=())
    with pytest.raises(MacroError):
        Macro(
            id="m1",
            name="Too long",
            steps=tuple(MacroStep("x.y") for _ in range(MAX_MACRO_STEPS + 1)),
        )
    with pytest.raises(MacroError):
        Macro(id="m1", name="Bad version", steps=(MacroStep("x.y"),), version=0)


def test_recorder_lifecycle() -> None:
    recorder = MacroRecorder(clock=FixedClock(start=42.0))
    assert recorder.is_recording is False
    with pytest.raises(MacroError):
        recorder.capture(CommandInvocation("x.y"))
    recorder.start("triage", description="Morning triage")
    assert recorder.is_recording
    with pytest.raises(MacroError):
        recorder.start("other")
    recorder.capture(CommandInvocation("navigation.goto", {"ref": "note:alpha"}))
    recorder.capture(CommandInvocation("session.start", {"label": "Triage"}))
    assert recorder.size == 2
    macro = recorder.stop()
    assert macro.name == "triage"
    assert macro.created_at == 42.0
    assert macro.command_ids == ("navigation.goto", "session.start")
    assert not recorder.is_recording
    with pytest.raises(MacroError):
        recorder.stop()


def test_recorder_rejects_empty_and_cancels() -> None:
    recorder = MacroRecorder()
    recorder.start("empty")
    with pytest.raises(MacroError):
        recorder.stop()
    recorder.capture(CommandInvocation("x.y"))
    recorder.cancel()
    assert recorder.size == 0
    assert not recorder.is_recording


def test_recorder_step_limit() -> None:
    recorder = MacroRecorder()
    recorder.start("big")
    for _ in range(MAX_MACRO_STEPS):
        recorder.capture(CommandInvocation("x.y"))
    with pytest.raises(MacroError):
        recorder.capture(CommandInvocation("x.y"))
    with pytest.raises(MacroError):
        recorder.start("another")


def test_macro_roundtrip_through_library() -> None:
    macro = Macro(
        id="macro_1",
        name="Review",
        steps=(MacroStep("navigation.goto", {"ref": "note:alpha"}),),
        tags=("review",),
        created_at=10.0,
    )
    library = MacroLibrary()
    assert library.add(macro) is macro
    with pytest.raises(MacroError):
        library.add(macro)
    assert library.get("macro_1") == macro
    assert library.find_by_name(" review ") == macro
    assert library.by_tag("REVIEW") == (macro,)
    assert library.all() == (macro,)
    snapshot = library.snapshot()
    rebuilt = MacroLibrary()
    rebuilt.load(snapshot)
    assert rebuilt.get("macro_1").command_ids == macro.command_ids
    assert rebuilt.size() == 1
    assert library.remove("macro_1")
    assert not library.remove("macro_1")
    with pytest.raises(MacroError):
        library.get("macro_1")


def test_library_rejects_malformed_snapshots() -> None:
    library = MacroLibrary()
    with pytest.raises(MacroError):
        library.load({"macros": "bad"})
    with pytest.raises(MacroError):
        library.load({"macros": ["bad"]})
    with pytest.raises(MacroError):
        library.load({"macros": [{"id": "x", "name": "X", "steps": "bad"}]})


def test_macro_from_dict_validation() -> None:
    payload = {
        "id": "macro_2",
        "name": "Flow",
        "steps": [{"command_id": "x.y", "arguments": {"a": 1}}],
        "tags": "bad",
    }
    with pytest.raises(MacroError):
        Macro.from_dict(payload)
    valid = Macro.from_dict(
        {
            "id": "macro_2",
            "name": "Flow",
            "steps": [{"command_id": "x.y", "arguments": {"a": "b"}, "note": "hi"}],
            "tags": ["ops"],
            "created_at": 5.0,
        }
    )
    assert valid.steps[0].arguments == {"a": "b"}
    assert valid.tags == ("ops",)


def test_expand_macro_substitutes_placeholders() -> None:
    macro = Macro(
        id="macro_3",
        name="Open",
        steps=(
            MacroStep("navigation.goto", {"ref": "{{target}}", "pane": "pane:{{ pane }}"}),
            MacroStep("session.start", {"label": "Review {{target}}"}),
        ),
    )
    expanded = expand_macro(macro, {"target": "note:alpha", "pane": "side"})
    assert [invocation.command_id for invocation in expanded] == [
        "navigation.goto",
        "session.start",
    ]
    assert expanded[0].arguments == {"ref": "note:alpha", "pane": "pane:side"}
    assert expanded[0].source == "macro"
    with pytest.raises(MacroError):
        expand_macro(macro, {"target": "note:alpha"})


def test_macros_contain_only_serializable_data() -> None:
    macro = Macro(
        id="macro_4",
        name="Data",
        steps=(MacroStep("x.y", {"a": "b"}),),
    )
    payload = macro.as_dict()
    assert isinstance(payload["steps"], list)
    assert all(isinstance(step, dict) for step in payload["steps"])
    assert macro_steps_as_data(macro) == [{"command_id": "x.y", "arguments": "[('a', 'b')]"}]
    assert not any(callable(value) for value in payload.values())
