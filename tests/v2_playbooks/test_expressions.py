from __future__ import annotations

import pytest

from redscribe.v2.playbooks.errors import ExpressionError
from redscribe.v2.playbooks.expressions import (
    build_condition_from_text,
    compare,
    describe_expression,
    evaluate_condition,
    evaluate_expression,
    expression_references,
    is_truthy,
    lookup_path,
    parse_expression,
    regex_matches,
    tokenize,
    validate_expression,
)
from redscribe.v2.playbooks.types import Condition, ConditionOperator, Values

VALUES: Values = {
    "target": "example.com",
    "port": 443,
    "ports": ("80", "443"),
    "empty": "",
    "disabled": "false",
    "zero": 0,
    "enabled": True,
}


def test_tokenize_covers_literals_operators_and_structures() -> None:
    tokens = tokenize("name == 'o\\'brien' && port >= 80")

    assert [token.kind for token in tokens] == [
        "name",
        "operator",
        "string",
        "operator",
        "name",
        "operator",
        "number",
        "eof",
    ]
    assert tokens[2].value == "o'brien"
    assert tokens[-1].position == len("name == 'o\\'brien' && port >= 80")


def test_tokenize_rejects_unterminated_string() -> None:
    with pytest.raises(ExpressionError, match="Unterminated string"):
        tokenize("'broken")


def test_parse_expression_builds_a_tree() -> None:
    expression = parse_expression("target == 'example.com' and port > 80")

    assert expression.describe() == "target = example.com and port > 80"


def test_parse_expression_rejects_empty_source() -> None:
    with pytest.raises(ExpressionError, match="empty"):
        parse_expression("   ")


def test_parse_expression_rejects_trailing_tokens() -> None:
    with pytest.raises(ExpressionError, match="Unexpected token"):
        parse_expression("target == 'example.com' nonsense")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("target == 'example.com'", True),
        ("target != 'example.com'", False),
        ("port >= 80", True),
        ("port < 80", False),
        ("target == 'EXAMPLE.COM'", True),
        ("enabled", True),
        ("disabled", False),
        ("zero", False),
    ],
)
def test_evaluate_expression_comparisons(source: str, expected: bool) -> None:
    assert evaluate_expression(source, VALUES) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("exists(target)", True),
        ("exists(missing)", False),
        ("not exists(missing)", True),
        ("empty(empty)", True),
        ("empty(target)", False),
        ("len(target) > 5", True),
        ("lower(target) == 'example.com'", True),
        ("upper(target) == 'EXAMPLE.COM'", True),
        ("contains(target, 'ample')", True),
        ("startswith(target, 'ex')", True),
        ("endswith(target, '.com')", True),
        ("matches(target, '^ex.*\\\\.com$')", True),
        ("default(missing, 'fallback') == 'fallback'", True),
        ("has_any(ports, '443,8080')", True),
    ],
)
def test_evaluate_expression_functions(source: str, expected: bool) -> None:
    assert evaluate_expression(source, VALUES) is expected


def test_evaluate_expression_supports_boolean_operators_and_lists() -> None:
    assert evaluate_expression("port > 80 && target == 'example.com'", VALUES)
    assert evaluate_expression("port < 80 || target == 'example.com'", VALUES)
    assert evaluate_expression("!disabled", VALUES)
    assert evaluate_expression("'443' in ports", VALUES)
    assert evaluate_expression("'22' not in ports", VALUES)
    assert evaluate_expression("port in [80, 443]", VALUES)
    assert evaluate_expression("port is 443", VALUES)
    assert evaluate_expression("port is not 80", VALUES)


def test_expression_references_are_unique_and_ordered() -> None:
    assert expression_references("target == port or target == domain") == (
        "target",
        "port",
        "domain",
    )
    assert expression_references("contains(target, 'x')") == ("target",)


def test_describe_expression_normalizes_operators() -> None:
    assert describe_expression("port >= 80 && target == 'example.com'") == (
        "port >= 80 and target = example.com"
    )
    assert describe_expression("not disabled") == "not disabled"


def test_validate_expression_reports_parser_errors() -> None:
    issues = validate_expression("target ==")

    assert len(issues) == 1
    assert issues[0].code == "invalid-expression"
    assert issues[0].is_error


def test_validate_expression_allows_valid_expressions() -> None:
    assert validate_expression("exists(target) and port > 80") == ()


@pytest.mark.parametrize(
    ("field_name", "operator", "value", "expected"),
    [
        ("target", ConditionOperator.EXISTS, "", True),
        ("missing", ConditionOperator.EXISTS, "", False),
        ("missing", ConditionOperator.NOT_EXISTS, "", True),
        ("empty", ConditionOperator.NOT_EXISTS, "", True),
        ("target", ConditionOperator.EQ, "EXAMPLE.COM", True),
        ("target", ConditionOperator.NE, "other.tld", True),
        ("port", ConditionOperator.GT, 80, True),
        ("port", ConditionOperator.GTE, 443, True),
        ("port", ConditionOperator.LT, 80, False),
        ("port", ConditionOperator.LTE, 443, True),
        ("target", ConditionOperator.CONTAINS, "ample", True),
        ("target", ConditionOperator.NOT_CONTAINS, "missing", True),
        ("target", ConditionOperator.MATCHES, "^ex.*\\.com$", True),
        ("port", ConditionOperator.IN, [80, 443], True),
        ("port", ConditionOperator.NOT_IN, [80, 8080], True),
    ],
)
def test_evaluate_condition_covers_all_operators(
    field_name: str,
    operator: ConditionOperator,
    value: object,
    expected: bool,
) -> None:
    condition = Condition(field=field_name, operator=operator, value=value)

    assert evaluate_condition(condition, VALUES) is expected


def test_evaluate_condition_accepts_string_operators() -> None:
    condition = Condition(field="target", operator="eq", value="example.com")

    assert condition.matches(VALUES)


def test_evaluate_condition_requires_a_field() -> None:
    with pytest.raises(ExpressionError, match="no field"):
        evaluate_condition(Condition(field="  "), VALUES)


def test_evaluate_condition_rejects_unknown_operator() -> None:
    condition = Condition(field="target")

    object.__setattr__(condition, "operator", "bogus")

    with pytest.raises(ValueError):
        evaluate_condition(condition, VALUES)


def test_lookup_path_supports_flat_and_tuple_paths() -> None:
    assert lookup_path(VALUES, "target") == "example.com"
    assert lookup_path(VALUES, "ports.1") == "443"
    assert lookup_path(VALUES, "ports.9") == ""
    assert lookup_path(VALUES, "missing.child") == ""


@pytest.mark.parametrize(
    ("left", "operator", "right", "expected"),
    [
        ("abc", "contains", "b", True),
        ("abc", "not contains", "z", True),
        ("abc", "in", "abcabc", True),
        ("abc", "not in", "def", True),
        ("10", ">", 2, True),
        ("10", "<", 2, False),
        ("true", "==", True, True),
        (("a", "b"), "==", ["a", "b"], False),
    ],
)
def test_compare_handles_scalars_and_tuples(
    left: object, operator: str, right: object, expected: bool
) -> None:
    assert compare(left, operator, right) is expected


def test_compare_returns_false_for_bad_ordering() -> None:
    assert compare("not-a-number", ">", 2) is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (("x",), True),
        ((), False),
        (" false ", False),
        ("none", False),
        ("value", True),
        (None, False),
    ],
)
def test_is_truthy_follows_domain_rules(value: object, expected: bool) -> None:
    assert is_truthy(value) is expected


def test_regex_matches_rejects_invalid_pattern() -> None:
    assert regex_matches("abc", "^a") is True
    assert regex_matches("abc", "") is False

    with pytest.raises(ExpressionError, match="Invalid regular expression"):
        regex_matches("abc", "[")


def test_build_condition_from_text_wraps_expression() -> None:
    condition = build_condition_from_text("target", "contains(target, 'ample')")

    assert condition.field == "target"
    assert condition.operator == ConditionOperator.EQ
    assert condition.value == "contains(target, 'ample')"


def test_build_condition_from_text_can_negate() -> None:
    condition = build_condition_from_text("target", "exists(target)", negate=True)

    assert condition.value == "not (exists(target))"


def test_build_condition_from_text_rejects_bad_expression() -> None:
    with pytest.raises(ExpressionError):
        build_condition_from_text("target", "target ==")


def test_condition_as_dict_and_describe_are_stable() -> None:
    condition = Condition(field="ports", operator=ConditionOperator.CONTAINS, value="443")

    assert condition.as_dict() == {
        "field": "ports",
        "operator": "contains",
        "value": "443",
    }
    assert condition.describe() == "ports contains 443"


def test_parse_expression_rejects_unknown_functions() -> None:
    with pytest.raises(ExpressionError, match="Unknown expression function"):
        parse_expression("evil(target)")


def test_expression_with_negative_number_evaluates() -> None:
    assert evaluate_expression("-port < 0", VALUES) is True
