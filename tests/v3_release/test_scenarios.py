"""Tests for golden-path scenario runners."""

from __future__ import annotations

import pytest

from redscribe.v3.release.models import ReleasePhase
from redscribe.v3.release.scenarios import (
    DETERMINISM_SCENARIO,
    GOLDEN_SCENARIO,
    IDEMPOTENCY_SCENARIO,
    REDACTION_SCENARIO,
    SCENARIO_DESCRIPTIONS,
    run_all_scenarios,
    run_determinism_scenario,
    run_golden_path,
    run_idempotency_scenario,
    run_redaction_scenario,
    run_scenario,
    scenario_manifest,
)


def test_golden_path_covers_all_phases() -> None:
    result = run_golden_path()
    assert result.ok is True
    assert result.name == GOLDEN_SCENARIO
    assert set(result.phases) == {phase.value for phase in ReleasePhase}
    assert len(result.steps) >= 20
    assert all(step.passed for step in result.steps)


def test_golden_path_is_deterministic_across_runs() -> None:
    first = run_golden_path()
    second = run_golden_path()
    assert [step.as_dict() for step in first.steps] == [step.as_dict() for step in second.steps]


def test_golden_path_accepts_custom_identity() -> None:
    result = run_golden_path(prefix="custom", start=5000.0)
    capture = next(step for step in result.steps if step.name == "note-created")
    assert capture.actual == "note:custom-note-capture"
    assert result.ok is True


def test_redaction_scenario() -> None:
    result = run_redaction_scenario()
    assert result.ok is True
    assert result.name == REDACTION_SCENARIO
    names = [step.name for step in result.steps]
    assert "api-key-hidden" in names
    assert "no-secret-in-bundle" in names


def test_idempotency_scenario() -> None:
    result = run_idempotency_scenario()
    assert result.ok is True
    assert result.name == IDEMPOTENCY_SCENARIO
    conflict = next(step for step in result.steps if step.name == "key-conflict")
    assert conflict.actual == "idempotency_conflict"


def test_determinism_scenario() -> None:
    result = run_determinism_scenario()
    assert result.ok is True
    assert result.name == DETERMINISM_SCENARIO
    tamper = next(step for step in result.steps if step.name == "tamper-detected")
    assert tamper.expected == "False"
    assert tamper.passed is True


def test_all_scenarios_pass() -> None:
    results = run_all_scenarios()
    assert len(results) == len(SCENARIO_DESCRIPTIONS)
    assert all(result.ok for result in results)
    assert {result.name for result in results} == set(SCENARIO_DESCRIPTIONS)


@pytest.mark.parametrize("name", sorted(SCENARIO_DESCRIPTIONS))
def test_run_scenario_by_name(name: str) -> None:
    result = run_scenario(name)
    assert result.name == name
    assert result.ok is True


def test_run_scenario_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown golden-path scenario"):
        run_scenario("not-a-scenario")


def test_scenario_manifest_shape() -> None:
    manifest = scenario_manifest()
    assert manifest["version"] == "3.0"
    assert manifest["phase_count"] == 7
    assert len(manifest["scenarios"]) == 4
    assert manifest["scenarios"][0]["phases"][0] == "capture"
    assert manifest["scenarios"][0]["phases"][-1] == "merge"


def test_scenario_results_have_documentation_strings() -> None:
    for result in run_all_scenarios():
        assert result.description
        assert result.description == SCENARIO_DESCRIPTIONS[result.name]
