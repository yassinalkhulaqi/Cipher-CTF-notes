"""Domain types and strict parsing of untrusted playbook payloads."""

from __future__ import annotations

import pytest

from redscribe.v3.automation.errors import PlaybookValidationError
from redscribe.v3.automation.parsing import (
    FORBIDDEN_INPUT_KEYS,
    parse_condition,
    parse_playbook,
    parse_recurrence,
    parse_step,
    parse_values,
    parse_variable,
)
from redscribe.v3.automation.types import (
    ConditionOperator,
    Frequency,
    PlaybookDefinition,
    RecurrenceRule,
    StepCondition,
    StepDefinition,
    StepKind,
    VariableKind,
)

from .helpers import playbook_payload


def test_step_kind_registry_is_closed() -> None:
    assert [kind.value for kind in StepKind] == [
        "create_note",
        "create_finding",
        "attach_evidence",
        "render_section",
        "emit_event",
    ]
    assert StepKind.parse(" CREATE_NOTE ") is StepKind.CREATE_NOTE
    assert StepKind.CREATE_NOTE.creates_entity is True
    assert StepKind.EMIT_EVENT.creates_entity is False
    with pytest.raises(ValueError):
        StepKind.parse("run_command")
    with pytest.raises(ValueError):
        VariableKind.parse("quantum")


def test_variable_definition_validation() -> None:
    definition = parse_variable({"key": "port", "kind": "number", "minimum": 1, "maximum": 9})
    assert definition.kind is VariableKind.NUMBER
    assert definition.key == "port"
    assert definition.as_dict()["minimum"] == 1
    assert definition.is_secret is False
    secret = parse_variable({"key": "token", "secret": True})
    assert secret.is_secret is True
    with pytest.raises(PlaybookValidationError):
        parse_variable({"label": "missing key"})
    with pytest.raises(ValueError):
        parse_variable({"key": "bad key"})
    with pytest.raises(ValueError):
        parse_variable({"key": "range", "minimum": 10, "maximum": 1})


def test_condition_matches_and_describes() -> None:
    condition = StepCondition(field="vars.count", operator=ConditionOperator.GTE, value=3)
    assert condition.matches({"vars": {"count": 4}}) is True
    assert condition.matches({"vars": {"count": 2}}) is False
    assert "gte" in condition.describe()
    assert ConditionOperator.EXISTS.value == "exists"
    assert StepCondition(field="vars.x").matches({"vars": {"x": 1}}) is True
    assert StepCondition(field="vars.x", operator=ConditionOperator.NOT_EXISTS).matches(
        {"vars": {}}
    )
    assert parse_condition({"field": "vars.a", "operator": "in", "value": [1, 2]}).matches(
        {"vars": {"a": 2}}
    )
    with pytest.raises(PlaybookValidationError):
        parse_condition({"field": "x", "operator": "regex"})


def test_step_and_playbook_parsing() -> None:
    playbook = parse_playbook(playbook_payload())
    assert isinstance(playbook, PlaybookDefinition)
    assert playbook.ref == "playbook:smoke"
    assert len(playbook.steps) == 4
    assert playbook.step("note").kind is StepKind.CREATE_NOTE
    assert playbook.variable("target") is not None
    assert playbook.variable("missing") is None
    assert playbook.as_dict()["variables"][1]["kind"] == "choice"
    with pytest.raises(KeyError):
        playbook.step("unknown")
    with pytest.raises(PlaybookValidationError):
        parse_step({"id": "x"})
    with pytest.raises(PlaybookValidationError):
        parse_step({"id": "x", "title": "X", "kind": "shell"})
    with pytest.raises(PlaybookValidationError):
        parse_playbook({"id": "broken", "steps": "not-a-list"})


@pytest.mark.parametrize("blocked", sorted(FORBIDDEN_INPUT_KEYS))
def test_command_like_inputs_are_rejected(blocked: str) -> None:
    payload = playbook_payload()
    payload["steps"][0]["inputs"][blocked] = "whoami"
    with pytest.raises(PlaybookValidationError, match="command-like keys"):
        parse_playbook(payload)


def test_parse_values_rejects_non_json_values() -> None:
    assert parse_values({"a": 1, "b": [1, 2], "c": {"d": True}}) == {
        "a": 1,
        "b": [1, 2],
        "c": {"d": True},
    }
    with pytest.raises(PlaybookValidationError):
        parse_values({"a": object()})


def test_recurrence_parsing_and_serialization() -> None:
    rule = parse_recurrence(
        {
            "frequency": "weekly",
            "interval": 2,
            "by_weekday": [0, 2],
            "hour": 7,
            "minute": 30,
            "count": 5,
        }
    )
    assert rule.frequency is Frequency.WEEKLY
    assert rule.by_weekday == (0, 2)
    assert rule.as_dict()["minute"] == 30
    assert RecurrenceRule().interval == 1
    with pytest.raises(PlaybookValidationError):
        parse_recurrence({"frequency": "yearly"})
    with pytest.raises(PlaybookValidationError):
        parse_recurrence({"frequency": "daily", "by_weekday": "Mon"})
    with pytest.raises(ValueError):
        RecurrenceRule(hour=25)
    with pytest.raises(ValueError):
        RecurrenceRule(by_month_day=32)


def test_immutable_records_reject_invalid_state() -> None:
    with pytest.raises(ValueError):
        StepDefinition(id="", title="x")
    with pytest.raises(ValueError):
        StepDefinition(id="has space", title="x")
    with pytest.raises(ValueError):
        StepDefinition(id="s", title="  ")
    with pytest.raises(ValueError):
        PlaybookDefinition(id="", title="x", steps=())
    with pytest.raises(ValueError):
        PlaybookDefinition(id="p", title="x", steps=(), version=0)
