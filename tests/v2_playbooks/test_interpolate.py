from __future__ import annotations

import pytest

from redscribe.v2.playbooks.errors import InterpolationError
from redscribe.v2.playbooks.interpolate import (
    apply_filter,
    mask_values,
    parse_expression,
    parse_tokens,
    render,
    render_strict,
    validate_source,
    variables_in,
)
from redscribe.v2.playbooks.types import Values

VALUES: Values = {
    "target": "Example.COM",
    "ports": ("80", "443"),
    "token": "supersecret",
    "empty": "",
}


def test_parse_expression_reads_name_and_inline_default() -> None:
    token = parse_expression(" target | upper ")

    assert token.name == "target"
    assert token.raw == "target | upper"
    assert [(item.name, item.arguments) for item in token.filters] == [("upper", ())]


def test_parse_expression_supports_inline_default_syntax() -> None:
    token = parse_expression("missing:'fallback value'")

    assert token.name == "missing"
    assert [(item.name, item.arguments) for item in token.filters] == [
        ("default", ("fallback value",))
    ]


def test_parse_expression_supports_literal_names() -> None:
    token = parse_expression("'literal' | upper")

    assert token.name == "'literal'"


@pytest.mark.parametrize(
    "source",
    ["", "| upper", "bad name | upper"],
)
def test_parse_expression_rejects_invalid_sources(source: str) -> None:
    with pytest.raises(InterpolationError):
        parse_expression(source)


def test_parse_tokens_preserves_literal_text() -> None:
    tokens = parse_tokens("Scan {{ target }} now")

    assert tokens[0] == "Scan "
    assert getattr(tokens[1], "name", "") == "target"
    assert tokens[2] == " now"


def test_parse_tokens_handles_empty_source() -> None:
    assert parse_tokens("") == ()


def test_variables_in_is_unique_and_ordered() -> None:
    assert variables_in("{{ target }} {{ ports }} {{ target }}") == ("target", "ports")


def test_variables_in_ignores_literals() -> None:
    assert variables_in("{{ 'literal' }}") == ()


def test_validate_source_reports_unknown_filters_as_warnings() -> None:
    issues = validate_source("{{ target | bogus }}")

    assert len(issues) == 1
    assert issues[0].code == "unknown-filter"
    assert issues[0].severity == "warning"
    assert issues[0].is_error is False


def test_validate_source_reports_unbalanced_braces() -> None:
    issues = validate_source("{{ target }")

    assert any(issue.code == "unbalanced-placeholder" for issue in issues)


def test_validate_source_accepts_clean_template() -> None:
    assert validate_source("{{ target | upper }}") == ()


def test_render_interpolates_values_and_records_usage() -> None:
    result = render("Host {{ target }} on {{ ports | join(':') }}", VALUES)

    assert result.text == "Host Example.COM on 80:443"
    assert result.used == ("target", "ports")
    assert result.unresolved == ()
    assert result.ok


def test_render_uses_undefined_placeholder_and_reports_warnings() -> None:
    result = render("{{ missing }} / {{ target }}", VALUES, undefined="n/a")

    assert result.text == "n/a / Example.COM"
    assert result.unresolved == ("missing",)
    assert any(issue.code == "unresolved-variable" for issue in result.issues)
    assert result.ok


def test_render_supports_inline_default() -> None:
    result = render("{{ missing:'fallback' }}", VALUES)

    assert result.text == "fallback"
    assert result.unresolved == ("missing",)


def test_render_does_not_raise_for_unknown_filter_but_reports_it() -> None:
    result = render("{{ target | bogus }}", VALUES)

    assert result.text == "Example.COM"
    assert any(issue.code == "filter-error" for issue in result.issues)
    assert result.ok


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("{{ target | upper }}", "EXAMPLE.COM"),
        ("{{ target | lower }}", "example.com"),
        ("{{ target | title }}", "Example.Com"),
        ("{{ target | capitalize }}", "Example.com"),
        ("{{ '  padded  ' | trim }}", "padded"),
        ("{{ 'My Target' | slug }}", "my-target"),
        ("{{ 'a b' | quote }}", '"a b"'),
        ("{{ 'a b' | shell }}", "'a b'"),
        ("{{ 'a' | json }}", '"a"'),
        ("{{ 'a' | base64 }}", "YQ=="),
        ("{{ 'a b' | urlencode }}", "a%20b"),
        ("{{ 'abcdef' | mask }}", "ab****"),
        ("{{ 'abcdef' | length }}", "6"),
        ("{{ empty | default('fallback') }}", "fallback"),
        ("{{ target | prefix('http://') }}", "http://Example.COM"),
        ("{{ target | suffix('/api') }}", "Example.COM/api"),
        ("{{ 'a-b' | replace('-', '_') }}", "a_b"),
        ("{{ '<b>' | escape }}", "&lt;b&gt;"),
        ("{{ 'a' | sha256 }}", "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"),
    ],
)
def test_apply_filter_and_render_filters(source: str, expected: str) -> None:
    assert render(source, VALUES).text == expected


def test_apply_filter_join_accepts_tuple_values() -> None:
    assert apply_filter("join", ("a", "b"), ("|",)) == "a|b"
    assert apply_filter("join", "a,b") == "a,b"


def test_apply_filter_coalesce_prefers_first_non_empty_argument() -> None:
    assert apply_filter("coalesce", "", ("primary", "secondary")) == "primary"
    assert apply_filter("coalesce", "value", ("primary",)) == "value"


def test_apply_filter_rejects_unknown_filter() -> None:
    with pytest.raises(InterpolationError, match="Unknown filter"):
        apply_filter("bogus", "value")


def test_render_strict_returns_clean_result() -> None:
    assert render_strict("{{ target }}", VALUES).text == "Example.COM"


def test_render_strict_raises_for_unresolved_variables() -> None:
    with pytest.raises(InterpolationError, match="Unresolved variables") as exc_info:
        render_strict("{{ missing }}", VALUES)

    assert exc_info.value.details == {"keys": ["missing"]}


def test_render_masks_values_when_filter_requests_it() -> None:
    result = render("{{ token | mask }}", VALUES, mask_secrets=True)

    assert result.text == "***"


def test_mask_values_masks_every_value() -> None:
    masked = mask_values(VALUES, visible=1)

    assert masked["target"] == "E********"
    assert masked["ports"] == "8*****"
    assert masked["token"] == "s********"


def test_mask_values_handles_empty_and_short_values() -> None:
    masked = mask_values({"empty": "", "short": "ab"}, visible=2)

    assert masked == {"empty": "", "short": "**"}


def test_render_handles_nested_filter_arguments() -> None:
    result = render("{{ target | replace('Example', 'my') | lower }}", VALUES)

    assert result.text == "my.com"


def test_render_rejects_placeholder_that_looks_like_code() -> None:
    with pytest.raises(InterpolationError, match="Invalid placeholder name"):
        render("{{ __import__('os').system('echo pwned') }}", VALUES)
