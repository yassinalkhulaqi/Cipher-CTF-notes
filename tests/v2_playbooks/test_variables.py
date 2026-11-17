from __future__ import annotations

from redscribe.v2.playbooks.types import VariableDefinition, VariableKind
from redscribe.v2.playbooks.variables import (
    BUILTIN_DEFINITIONS,
    BUILTIN_KEYS,
    coerce_value,
    derive_values,
    mask_known,
    masked_values,
    normalize_value,
    normalize_values,
    resolve_variables,
    suggest_variables,
    variable_options,
)


def test_normalize_value_handles_supported_and_unsupported_values() -> None:
    assert normalize_value(None) is None
    assert normalize_value(True) is True
    assert normalize_value(7) == 7
    assert normalize_value(1.5) == 1.5
    assert normalize_value("text") == "text"
    assert normalize_value([1, "two", True]) == ("1", "two", "True")
    assert normalize_value({"key": "value"}) == "{'key': 'value'}"


def test_normalize_values_drops_empty_keys_and_none_values() -> None:
    result = normalize_values({" target ": "example.com", "": "ignored", "missing": None, "n": 7})

    assert result == {"target": "example.com", "n": 7}


def test_normalize_values_ignores_non_mappings() -> None:
    assert normalize_values(["target"]) == {}


def test_derive_values_from_url_sets_related_variables() -> None:
    values = derive_values("https://app.example.com:8443/report?q=1", base={"operator": "alice"})

    assert values["target"] == "https://app.example.com:8443/report?q=1"
    assert values["scheme"] == "https"
    assert values["host"] == "app.example.com"
    assert values["domain"] == "app.example.com"
    assert "ip" not in values
    assert values["port"] == 8443
    assert values["slug"] == "app-example-com"
    assert values["path"] == "/report"
    assert values["operator"] == "alice"
    assert values["date"]
    assert values["time"]


def test_derive_values_from_ip_and_hostname() -> None:
    ip_values = derive_values("192.168.0.10")
    host_values = derive_values("localhost")

    assert ip_values["ip"] == "192.168.0.10"
    assert ip_values["slug"] == "192-168-0-10"
    assert host_values["host"] == "localhost"
    assert host_values["url"] == "http://localhost"


def test_derive_values_without_target_still_sets_environment() -> None:
    values = derive_values()

    assert values["operator"] == "redscribe"
    assert "target" not in values
    assert values["date"]
    assert values["time"]


def test_resolve_variables_marks_missing_required_values() -> None:
    definitions = (VariableDefinition("target", required=True),)

    result = resolve_variables(definitions, {})

    assert result.missing == ("target",)
    assert not result.ok
    assert "target" not in result.values


def test_resolve_variables_uses_defaults_for_optional_values() -> None:
    definitions = (
        VariableDefinition("target", required=True),
        VariableDefinition("ports", kind=VariableKind.LIST, default="80,443"),
    )

    result = resolve_variables(definitions, {"target": "example.com"})

    assert result.values["ports"] == ("80", "443")
    assert result.missing == ()
    assert result.ok


def test_resolve_variables_derives_context_from_target() -> None:
    definitions = (VariableDefinition("target", required=True),)

    result = resolve_variables(definitions, {}, target="example.com")

    assert result.values["target"] == "example.com"
    assert result.values["host"] == "example.com"
    assert "host" in result.derived
    assert "target" in result.derived


def test_resolve_variables_reports_invalid_values() -> None:
    definitions = (VariableDefinition("port", kind=VariableKind.NUMBER, minimum=1, maximum=65535),)

    high = resolve_variables(definitions, {"port": "70000"})
    invalid = resolve_variables(definitions, {"port": "many"})

    assert [issue.code for issue in high.invalid] == ["above-maximum"]
    assert [issue.code for issue in invalid.invalid] == ["invalid-number"]


def test_resolve_variables_strict_mode_reports_unknown_values() -> None:
    definitions = (VariableDefinition("target", required=True),)

    result = resolve_variables(
        definitions, {"target": "example.com", "custom": "value"}, strict=True
    )

    assert [issue.code for issue in result.warnings] == ["unknown-variable"]


def test_resolve_variables_reveals_non_secret_values_in_dict() -> None:
    definitions = (VariableDefinition("target", required=True),)
    result = resolve_variables(definitions, {"target": "example.com"})

    assert result.as_dict()["values"]["target"] == "example.com"
    assert result.as_dict()["ok"] is True


def test_resolve_variables_masks_secret_hints_in_dict() -> None:
    definitions = (VariableDefinition("password", kind=VariableKind.SECRET),)
    result = resolve_variables(definitions, {"password": "hunter2"})

    assert result.as_dict()["values"]["password"] == "***"


def test_coerce_value_text_and_secret() -> None:
    for kind in (VariableKind.TEXT, VariableKind.SECRET):
        definition = VariableDefinition("value", kind=kind)
        value, issues = coerce_value(definition, 42)

        assert value == "42"
        assert issues == ()


def test_coerce_value_number_accepts_int_and_float_strings() -> None:
    integer, integer_issues = coerce_value(VariableDefinition("n", kind=VariableKind.NUMBER), "42")
    decimal, decimal_issues = coerce_value(VariableDefinition("n", kind=VariableKind.NUMBER), "4.2")

    assert integer == 42
    assert integer_issues == ()
    assert decimal == 4.2
    assert decimal_issues == ()


def test_coerce_value_boolean_accepts_common_spellings() -> None:
    definition = VariableDefinition("flag", kind=VariableKind.BOOLEAN)

    assert coerce_value(definition, "yes")[0] is True
    assert coerce_value(definition, "OFF")[0] is False
    assert coerce_value(definition, "maybe")[1][0].code == "invalid-boolean"


def test_coerce_value_list_splits_commas() -> None:
    definition = VariableDefinition("hosts", kind=VariableKind.LIST)

    assert coerce_value(definition, "a, b ,,c")[0] == ("a", "b", "c")
    assert coerce_value(definition, ("a", "b"))[0] == ("a", "b")


def test_coerce_value_validates_choices_pattern_and_range() -> None:
    choice = VariableDefinition("level", choices=("low", "high"))
    pattern = VariableDefinition("code", pattern=r"^[A-Z]{3}$")
    ranged = VariableDefinition("n", kind=VariableKind.NUMBER, minimum=1, maximum=10)

    assert coerce_value(choice, "medium")[1][0].code == "invalid-choice"
    assert coerce_value(pattern, "abc")[1][0].code == "pattern-mismatch"
    assert coerce_value(ranged, 0)[1][0].code == "below-minimum"


def test_coerce_value_reports_invalid_pattern() -> None:
    definition = VariableDefinition("code", pattern="[")

    assert coerce_value(definition, "abc")[1][0].code == "invalid-pattern"


def test_variable_options_are_api_ready() -> None:
    options = variable_options(BUILTIN_DEFINITIONS)

    assert options[0]["key"] == "target"
    assert options[0]["label"] == "Target"
    assert any(item["secret"] for item in options)


def test_suggest_variables_ranks_by_key_label_and_description() -> None:
    definitions = (
        VariableDefinition("target", "Target", description="Scope target"),
        VariableDefinition("other", "Target alias"),
    )

    assert [item.key for item in suggest_variables(definitions, "target")] == ["target", "other"]


def test_suggest_variables_limit_and_empty_query() -> None:
    assert [item.key for item in suggest_variables(BUILTIN_DEFINITIONS, "", limit=2)] == [
        "target",
        "domain",
    ]
    assert suggest_variables(BUILTIN_DEFINITIONS, "nonexistent") == []


def test_mask_known_masks_hints_and_explicit_keys() -> None:
    values = {"token": "abc", "api_key": "def", "target": "example.com"}

    assert mask_known(values, ("target",)) == {
        "token": "***",
        "api_key": "***",
        "target": "***",
    }


def test_masked_values_masks_every_value() -> None:
    assert masked_values({"target": "example.com", "port": 443}) == {
        "target": "e********",
        "port": "4**",
    }


def test_builtin_keys_and_definitions_are_stable() -> None:
    assert "target" in BUILTIN_KEYS
    assert "password" in BUILTIN_KEYS
    assert {item.key for item in BUILTIN_DEFINITIONS}.issubset(set(BUILTIN_KEYS))
