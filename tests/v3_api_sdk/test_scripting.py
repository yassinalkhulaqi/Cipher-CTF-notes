"""Declarative script validation and execution."""

from __future__ import annotations

import pytest

from redscribe.v3.api_sdk.errors import ReadOnlyViolationError, ScriptError
from redscribe.v3.api_sdk.scripting import (
    MAX_STEPS,
    ScriptPlan,
    ScriptResult,
    ScriptRunner,
    ScriptStep,
    StepOutcome,
    example_script,
)


def test_script_step_parses_and_renders() -> None:
    step = ScriptStep.from_dict(
        {
            "label": "health",
            "namespace": "system",
            "action": "info",
            "body": {"echo": "x"},
            "capability": "extensions",
            "etag": '"tag"',
            "idempotency_key": "key",
            "write": False,
        }
    )
    assert step.label == "health"
    assert step.write is False
    assert step.capability == "extensions"
    assert step.as_dict()["idempotency_key"] == "key"


def test_script_step_rejects_unknown_fields_and_bad_types() -> None:
    with pytest.raises(ScriptError):
        ScriptStep.from_dict({"namespace": "system", "action": "info", "code": "x"})
    with pytest.raises(ScriptError):
        ScriptStep.from_dict({"namespace": "system", "body": {}})
    with pytest.raises(ScriptError):
        ScriptStep.from_dict({"namespace": "system", "action": "info", "body": [1, 2]})
    with pytest.raises(ScriptError):
        ScriptStep.from_dict({"namespace": "system", "action": "info", "label": "x" * 300})
    with pytest.raises(ScriptError):
        ScriptStep.from_dict({"namespace": "system", "action": "info", "capability": "x" * 300})


def test_script_plan_from_example_is_read_only() -> None:
    plan = ScriptPlan.from_document(example_script())
    assert plan.name == "local-overview"
    assert plan.read_only
    assert plan.write_steps == ()
    assert len(plan.steps) == 3
    assert plan.as_dict()["steps"][0]["namespace"] == "system"
    plan.validate()


def test_script_plan_rejects_invalid_documents() -> None:
    with pytest.raises(ScriptError):
        ScriptPlan.from_document([])  # type: ignore[arg-type]
    with pytest.raises(ScriptError):
        ScriptPlan.from_document({"name": "x", "steps": [], "eval": "1"})
    with pytest.raises(ScriptError):
        ScriptPlan.from_document({"name": "", "steps": [{"namespace": "a", "action": "b"}]})
    with pytest.raises(ScriptError):
        ScriptPlan.from_document({"name": "x", "steps": {}})
    document = {
        "name": "x",
        "steps": [
            {"namespace": "system", "action": "info", "write": False} for _ in range(MAX_STEPS + 1)
        ],
    }
    with pytest.raises(ScriptError):
        ScriptPlan.from_document(document)


def test_write_plan_requires_explicit_opt_in() -> None:
    document = {
        "name": "install",
        "steps": [
            {
                "namespace": "extensions",
                "action": "install",
                "body": {"manifest": {}, "allow_write": True},
                "write": True,
            }
        ],
    }
    plan = ScriptPlan.from_document(document)
    assert not plan.read_only
    assert len(plan.write_steps) == 1
    with pytest.raises(ReadOnlyViolationError):
        plan.validate()
    plan.validate(allow_write=True)
    permitted = ScriptPlan.from_document({**document, "allow_write": True})
    permitted.validate()


def test_runner_executes_read_only_script(client: object) -> None:
    from redscribe.v3.api_sdk.client import SdkClient

    assert isinstance(client, SdkClient)
    result = ScriptRunner(client).run(ScriptPlan.from_document(example_script()))
    assert result.success
    assert not result.stopped_early
    assert len(result.outcomes) == 3
    assert all(item.ok for item in result.outcomes)
    assert result.as_dict()["steps"][0]["status"] == 200
    assert client.history.size() == 3


def test_runner_refuses_write_before_any_step(client: object) -> None:
    from redscribe.v3.api_sdk.client import SdkClient

    assert isinstance(client, SdkClient)
    plan = ScriptPlan.from_document(
        {
            "name": "blocked",
            "steps": [
                {"namespace": "system", "action": "info"},
                {
                    "namespace": "extensions",
                    "action": "remove",
                    "body": {"id": "example.panel", "allow_write": True},
                    "write": True,
                },
            ],
        }
    )
    with pytest.raises(ReadOnlyViolationError):
        ScriptRunner(client).run(plan)
    assert client.history.size() == 0


def test_runner_installs_and_removes_with_opt_in(
    writable_client: object, sample_manifest: dict[str, object]
) -> None:
    from redscribe.v3.api_sdk.client import SdkClient

    assert isinstance(writable_client, SdkClient)
    plan = ScriptPlan.from_document(
        {
            "name": "install-then-remove",
            "steps": [
                {
                    "label": "install",
                    "namespace": "extensions",
                    "action": "install",
                    "body": {"manifest": sample_manifest, "allow_write": True},
                    "write": True,
                },
                {
                    "label": "remove",
                    "namespace": "extensions",
                    "action": "remove",
                    "body": {"id": "example.panel", "allow_write": True},
                    "write": True,
                },
            ],
        }
    )
    result = ScriptRunner(writable_client).run(plan, allow_write=True)
    assert result.success
    assert [item.label for item in result.outcomes] == ["install", "remove"]


def test_runner_stops_or_continues_on_error(client: object) -> None:
    from redscribe.v3.api_sdk.client import SdkClient

    assert isinstance(client, SdkClient)
    plan = ScriptPlan.from_document(
        {
            "name": "mixed",
            "steps": [
                {"namespace": "extensions", "action": "get", "body": {}},
                {"namespace": "system", "action": "info"},
            ],
        }
    )
    stopped = ScriptRunner(client).run(plan)
    assert stopped.stopped_early
    assert len(stopped.outcomes) == 1
    assert not stopped.success
    continued = ScriptRunner(client).run(plan, continue_on_error=True)
    assert not continued.stopped_early
    assert len(continued.outcomes) == 2
    assert continued.outcomes[0].error_code == "invalid_type"
    assert continued.outcomes[1].ok


def test_outcome_and_result_serialization() -> None:
    outcome = StepOutcome(
        index=0,
        label="step",
        namespace="system",
        action="info",
        status=200,
        ok=True,
        error_code="",
        data={"ok": True},
        request_id="req_1",
    )
    payload = outcome.as_dict()
    assert payload["route"] == "/api/v3/system/info"
    result = ScriptResult(name="x", outcomes=(outcome,))
    assert result.success
    assert result.as_dict()["stopped_early"] is False
