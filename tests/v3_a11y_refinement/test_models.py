"""Contract model tests for the V3 a11y refinement layer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from redscribe.v2.a11y.models import Direction, PreferenceSnapshot, WcagLevel
from redscribe.v3.a11y_refinement.models import (
    AuditRun,
    ContrastTarget,
    FormatRequest,
    KeyboardBinding,
    MotionMode,
    PreferenceSyncRecord,
    RuleFinding,
    RuleScope,
    SurfaceSpec,
    SyncStrategy,
    WcagRule,
)


def test_surface_spec_defaults_and_serialization() -> None:
    spec = SurfaceSpec(name="test-surface", label="Test surface")
    payload = spec.as_dict()
    assert payload["name"] == "test-surface"
    assert payload["level"] == "AA"
    assert payload["locale"] == "en"
    assert payload["target_size"] == 32
    assert payload["tiles"] == []
    assert spec.focus_obscured == "none"
    assert spec.keyboard_reachable is True


def test_surface_spec_is_frozen() -> None:
    spec = SurfaceSpec(name="a", label="A")
    with pytest.raises(FrozenInstanceError):
        spec.name = "b"  # type: ignore[misc]


def test_wcag_rule_serialization() -> None:
    rule = WcagRule(
        rule_id="pointer.target_size",
        criterion="2.5.8",
        title="Target Size (Minimum)",
        level=WcagLevel.AA,
        scope=RuleScope.POINTER,
        description="desc",
        remediation="fix",
    )
    payload = rule.as_dict()
    assert payload["id"] == "pointer.target_size"
    assert payload["criterion"] == "2.5.8"
    assert payload["level"] == "AA"
    assert payload["automated"] is True


def test_audit_run_passed_logic() -> None:
    clean = AuditRun(surface="clean", level=WcagLevel.AA, score=100.0)
    assert clean.passed is True
    assert clean.as_dict()["passed"] is True
    blocking = AuditRun(
        surface="bad",
        level=WcagLevel.AA,
        findings=(
            RuleFinding(
                rule_id="x",
                criterion="1.1.1",
                severity="moderate",
                target="bad",
                message="m",
                remediation="r",
            ),
        ),
    )
    assert blocking.passed is False


def test_contrast_and_format_models_are_json_safe() -> None:
    target = ContrastTarget(name="body", foreground="#000000", background="#ffffff")
    assert target.as_dict()["graphical"] is False
    request = FormatRequest(locale="de-DE", kind="number", value=10, options={"digits": 2})
    payload = request.as_dict()
    assert payload["locale"] == "de-DE"
    assert payload["options"] == {"digits": 2}


def test_keyboard_binding_payload() -> None:
    binding = KeyboardBinding(
        action="save",
        keys=("ctrl", "s"),
        label="Save",
        group="editing",
        scope="editor",
        display="Ctrl+S",
        sequence=2,
    )
    payload = binding.as_dict()
    assert payload["keys"] == ["ctrl", "s"]
    assert payload["display"] == "Ctrl+S"
    assert payload["sequence"] == 2


def test_enums_have_stable_values() -> None:
    assert MotionMode.REDUCED.value == "reduced"
    assert SyncStrategy.REMOTE_WINS.value == "remote_wins"
    assert Direction.RTL.value == "rtl"


def test_preference_sync_record_payload() -> None:
    snapshot = PreferenceSnapshot(locale="ar", theme="light", direction=Direction.RTL)
    record = PreferenceSyncRecord(
        profile="work",
        snapshot=snapshot,
        revision=4,
        checksum="abc123",
        tags=("v3", "rtl"),
    )
    payload = record.as_dict()
    assert payload["profile"] == "work"
    assert payload["checksum"] == "abc123"
    assert payload["preferences"]["direction"] == "rtl"
    assert payload["tags"] == ["v3", "rtl"]
