"""Query template rendering, validation, and discovery."""

from __future__ import annotations

import pytest

from redscribe.v3.search_intel.templates import (
    TemplateRegistry,
    default_templates,
    extract_placeholders,
    render_template,
    render_value,
)
from redscribe.v3.search_intel.types import QueryTemplate


def test_extract_placeholders_preserves_order() -> None:
    assert extract_placeholders("kind:{kind} tag:{tag} kind:{kind}") == ("kind", "tag")


def test_render_value_prefers_bare_safe_tokens() -> None:
    assert render_value("finding") == "finding"
    assert render_value("2024-01-01") == "2024-01-01"


def test_render_value_quotes_and_escapes() -> None:
    assert render_value('say "hi"') == '"say \\"hi\\""'


def test_render_template_substitutes_all_placeholders() -> None:
    template = QueryTemplate(id="t", name="T", pattern="kind:{kind} status:{status}")
    rendered = render_template(template, {"kind": "finding", "status": "active"})
    assert rendered == "kind:finding status:active"


def test_render_template_requires_all_values() -> None:
    template = QueryTemplate(id="t", name="T", pattern="kind:{kind} tag:{tag}")
    with pytest.raises(ValueError, match="Missing template values"):
        render_template(template, {"kind": "finding"})


def test_render_template_rejects_unknown_values() -> None:
    template = QueryTemplate(id="t", name="T", pattern="kind:{kind}")
    with pytest.raises(ValueError, match="Unknown template values"):
        render_template(template, {"kind": "finding", "extra": "x"})


def test_render_template_rejects_blank_values() -> None:
    template = QueryTemplate(id="t", name="T", pattern="kind:{kind}")
    with pytest.raises(ValueError, match="cannot be empty"):
        render_template(template, {"kind": "  "})


def test_default_templates_have_consistent_placeholders() -> None:
    for template in default_templates():
        assert template.placeholders == extract_placeholders(template.pattern)


def test_registry_lists_and_gets() -> None:
    registry = TemplateRegistry()
    assert len(registry.list()) >= 8
    assert registry.get("critical-findings") is not None
    assert registry.get("missing") is None


def test_registry_render() -> None:
    registry = TemplateRegistry()
    assert registry.render("critical-findings", {}) == "kind:finding severity:critical"


def test_registry_render_unknown_template() -> None:
    registry = TemplateRegistry()
    with pytest.raises(KeyError):
        registry.render("missing", {})


def test_registry_rejects_duplicates() -> None:
    registry = TemplateRegistry()
    with pytest.raises(ValueError, match="already registered"):
        registry.add(default_templates()[0])


def test_registry_filters_by_category() -> None:
    registry = TemplateRegistry()
    assert all(item.category == "pivot" for item in registry.list(category="pivot"))


def test_registry_suggests_by_intent() -> None:
    registry = TemplateRegistry()
    suggestions = registry.suggest("critical findings")
    assert any(item.id == "critical-findings" for item in suggestions)
    assert registry.suggest("")[0].id == registry.list()[0].id


def test_suggest_limit() -> None:
    registry = TemplateRegistry()
    assert len(registry.suggest("finding report evidence", limit=2)) <= 2
