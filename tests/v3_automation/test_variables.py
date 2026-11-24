"""Typed variable validation, interpolation and secret redaction."""

from __future__ import annotations

import pytest

from redscribe.v3.automation.errors import VariableResolutionError
from redscribe.v3.automation.types import (
    PlaybookDefinition,
    StepDefinition,
    VariableDefinition,
    VariableKind,
)
from redscribe.v3.automation.variables import (
    collect_placeholders,
    fingerprint_values,
    interpolate,
    placeholder_report,
    resolve_inputs,
    validate_values,
)

from .helpers import typed_variables


def _playbook(*variables: VariableDefinition) -> PlaybookDefinition:
    return PlaybookDefinition(id="vars", title="Variables", steps=(), variables=variables)


def test_numeric_coercion_and_bounds() -> None:
    playbook = _playbook(
        VariableDefinition(key="count", kind=VariableKind.NUMBER, minimum=1, maximum=5, default=2)
    )
    assert validate_values(playbook).values["count"] == 2
    assert validate_values(playbook, {"count": "4"}).values["count"] == 4
    result = validate_values(playbook, {"count": 99})
    assert result.ok is False
    assert result.issues[0].code == "out_of_range"
    assert validate_values(playbook, {"count": True}).ok is False
    assert validate_values(playbook, {"count": "abc"}).ok is False


def test_boolean_choice_list_and_entity_ref_types() -> None:
    playbook = _playbook(
        VariableDefinition(key="flag", kind=VariableKind.BOOLEAN, default=False),
        VariableDefinition(key="level", kind=VariableKind.CHOICE, choices=("low", "high")),
        VariableDefinition(key="tags", kind=VariableKind.LIST),
        VariableDefinition(key="ref", kind=VariableKind.ENTITY_REF),
    )
    resolution = validate_values(
        playbook,
        {"flag": "yes", "level": "high", "tags": "a,b,c", "ref": "evidence:item-1"},
    )
    assert resolution.ok is True
    assert resolution.values["flag"] is True
    assert resolution.values["tags"] == ["a", "b", "c"]
    assert validate_values(playbook, {"level": "critical"}).issues[0].code == "invalid_choice"
    ref_problem = validate_values(playbook, {"ref": "not-a-ref"})
    assert any(issue.code == "invalid_ref" for issue in ref_problem.issues)
    assert validate_values(playbook, {"tags": 7}).ok is False


def test_required_defaults_and_unknown_variables() -> None:
    playbook = _playbook(
        VariableDefinition(key="required", required=True),
        VariableDefinition(key="optional", default="fallback"),
    )
    missing = validate_values(playbook)
    assert missing.ok is False
    assert missing.issues[0].code == "missing_variable"
    assert missing.values["optional"] == "fallback"
    extra = validate_values(playbook, {"required": "ok", "bogus": 1})
    assert any(issue.code == "unknown_variable" for issue in extra.issues)
    with pytest.raises(VariableResolutionError):
        missing.raise_if_invalid()


def test_pattern_validation() -> None:
    playbook = _playbook(VariableDefinition(key="slug", pattern=r"[a-z0-9-]+"))
    assert validate_values(playbook, {"slug": "abc-123"}).ok is True
    assert validate_values(playbook, {"slug": "UPPER"}).issues[0].code == "invalid_pattern"


def test_interpolation_preserves_types_and_traverses_paths() -> None:
    context = {
        "vars": {"count": 7, "flag": False, "nested": {"key": "value"}},
        "steps": {"note": {"ref": "note:abc", "kind": "create_note"}},
    }
    assert interpolate("{{ count }}", context) == 7
    assert interpolate("{{ vars.flag }}", context) is False
    assert interpolate("n={{ vars.count }}", context) == "n=7"
    assert interpolate("{{ vars.nested.key }}", context) == "value"
    assert interpolate("{{ steps.note.ref }}", context) == "note:abc"
    assert interpolate("literal", context) == "literal"
    with pytest.raises(VariableResolutionError):
        interpolate("{{ missing }}", context)
    assert interpolate("{{ missing }}", context, strict=False) == ""


def test_placeholder_reporting() -> None:
    assert collect_placeholders("{{ a }} and {{ b }} and {{ a }}") == ("a", "b")
    assert collect_placeholders("none") == ()
    report = placeholder_report({"title": "{{ a }}", "body": ["{{ b }}"]})
    assert report["title"] == ("a",)
    assert report["body"] == ("b",)


def test_resolve_inputs_is_recursive_and_detached() -> None:
    context = {"vars": {"name": "alpha", "n": 3}}
    source = {
        "title": "Hello {{ name }}",
        "n": "{{ n }}",
        "items": ["{{ name }}", 4],
        "nested": {"body": "x{{ n }}"},
    }
    resolved = resolve_inputs(source, context)
    assert resolved == {
        "title": "Hello alpha",
        "n": 3,
        "items": ["alpha", 4],
        "nested": {"body": "x3"},
    }
    resolved["items"].append("changed")
    assert len(source["items"]) == 2


def test_secret_values_are_masked_everywhere() -> None:
    playbook = _playbook(
        VariableDefinition(key="token", secret=True),
        VariableDefinition(key="public", default="visible"),
    )
    resolution = validate_values(playbook, {"token": "super-secret", "public": "shown"})
    safe = resolution.as_dict()
    assert safe["values"]["token"] == "***"
    assert safe["values"]["public"] == "shown"
    assert "super-secret" not in str(safe)
    assert resolution.context()["vars"]["token"] == "super-secret"
    assert resolution.secrets == frozenset({"token"})
    assert fingerprint_values({"a": 1}) == fingerprint_values({"a": 1})
    assert fingerprint_values({"a": 1}) != fingerprint_values({"a": 2})


def test_typed_helpers_fixture() -> None:
    variables = typed_variables()
    assert variables[0].key == "target"
    assert variables[1].kind is VariableKind.NUMBER
    playbook = PlaybookDefinition(
        id="p",
        title="P",
        steps=(StepDefinition(id="s", title="S"),),
        variables=variables,
    )
    assert playbook.variables[0].required is True
