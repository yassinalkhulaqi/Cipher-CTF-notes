from __future__ import annotations

from redscribe.content.placeholders import (
    base_name,
    escape_placeholders,
    expression_names,
    interpolate,
    parse_placeholders,
    placeholder_names,
    render_expressions,
    resolve_path,
    target_values,
    unescape_placeholders,
    validate_expression,
)


def test_placeholder_names_are_unique_and_ordered() -> None:
    assert placeholder_names("{{user}}@{{target}} {{user}} {{lport}}") == [
        "user",
        "target",
        "lport",
    ]
    assert placeholder_names("no placeholders") == []


def test_interpolate_replaces_values_and_keeps_unknown() -> None:
    result = interpolate(
        "{{user}}@{{target}} {{unknown}} {{blank}}",
        {"user": " alice ", "target": "10.0.0.5", "blank": "  "},
    )
    assert result == "alice@10.0.0.5 {{unknown}} {{blank}}"


def test_target_values_derives_url_context() -> None:
    values = target_values("https://app.acme.test:8443/login?next=/admin")
    assert values["target"] == "https://app.acme.test:8443/login?next=/admin"
    assert values["domain"] == "app.acme.test"
    assert values["url"] == "https://app.acme.test:8443/login?next=/admin"
    assert values["slug"]


def test_target_values_accepts_host_port_and_path() -> None:
    values = target_values("10.10.10.10:8080/admin")
    assert values["domain"] == "10.10.10.10"
    assert values["url"] == "https://10.10.10.10:8080/admin"


def test_target_values_handles_ipv6() -> None:
    values = target_values("http://[2001:db8::1]:8080/path")
    assert values["domain"] == "2001:db8::1"
    assert values["url"] == "http://[2001:db8::1]:8080/path"


def test_empty_target_has_no_context() -> None:
    assert target_values("   ") == {}


def test_parse_placeholders_produces_positioned_tokens() -> None:
    tokens = parse_placeholders("{{user}}@{{domain}}")
    assert [(token.kind, token.name) for token in tokens] == [
        ("placeholder", "user"),
        ("text", ""),
        ("placeholder", "domain"),
    ]
    assert [token.position for token in tokens] == [0, 8, 9]
    assert tokens[0].raw == "{{user}}"
    assert tokens[2].filters == ()


def test_parse_placeholders_treats_escaped_and_invalid_spans_as_text() -> None:
    escaped = parse_placeholders(r"\{{raw}} {{live}}")
    assert escaped[0].raw == "{{raw}} "
    assert escaped[0].kind == "text"
    assert escaped[1].name == "live"

    invalid = parse_placeholders("{{bad name}} {{ok}}")
    assert invalid[0].kind == "text"
    assert invalid[0].raw == "{{bad name}}"
    assert invalid[2].name == "ok"


def test_render_expressions_applies_filter_chains() -> None:
    result = render_expressions(
        "{{name | upper}} {{name|lower}} {{target|slug}}",
        {"name": " Alice ", "target": "App Acme Test"},
    )
    assert result.text == "ALICE alice app-acme-test"
    assert result.unresolved == ()


def test_render_expressions_resolves_dotted_paths_and_defaults() -> None:
    assert render_expressions("{{ctx.user|upper}}", {"ctx": {"user": "alice"}}).text == "ALICE"
    assert render_expressions("{{x|default:fallback}}", {}).text == "fallback"
    assert render_expressions("{{x|prefix:pre|suffix:post}}", {"x": "mid"}).text == "premidpost"


def test_render_expressions_reports_unresolved_names() -> None:
    result = render_expressions("{{missing}} {{other}}", {})
    assert result.text == "{{missing}} {{other}}"
    assert result.unresolved == ("missing", "other")
    assert render_expressions("{{missing}}", {}, keep_unresolved=False).text == ""


def test_resolve_path_and_expression_names() -> None:
    assert resolve_path("a.b.c", {"a": {"b": {"c": " value "}}}) == "value"
    assert resolve_path("a.missing", {"a": {}}) == ""
    assert resolve_path("a", {}) == ""
    assert expression_names("{{user}} {{target | upper}} {{user}}") == ["user", "target"]
    assert base_name("target.domain") == "target"


def test_validate_expression_detects_bad_paths_and_filters() -> None:
    assert validate_expression("target|upper") == ()
    assert validate_expression("")[0].code == "invalid-path"
    assert validate_expression("bad name")[0].code == "invalid-path"
    issues = validate_expression("target|bogus")
    assert [issue.code for issue in issues] == ["unknown-filter"]
    assert issues[0].severity == "warning"


def test_escaping_placeholders_keeps_literal_text() -> None:
    text = "literal {{token}}"
    escaped = escape_placeholders(text)
    assert escaped == r"literal \{{token}}"
    assert unescape_placeholders(escaped) == text
    assert expression_names(escaped) == []
