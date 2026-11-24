"""Tests for the design engine, specification parsing, and determinism."""

from __future__ import annotations

from dataclasses import replace

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.entities.types import EntityRef
from redscribe.v3.report_designer.dto import parse_finding, parse_format, spec_from_dict
from redscribe.v3.report_designer.engine import (
    DesignSpec,
    ReportDesignerEngine,
    default_engine,
    design_key,
)
from redscribe.v3.report_designer.model import LayoutSection, SectionKind
from redscribe.v3.report_designer.renderers import HTML, JSON, MARKDOWN, PRINT
from redscribe.v3.report_designer.themes import ThemeRegistry


def test_design_pipeline(spec: DesignSpec, engine: ReportDesignerEngine) -> None:
    result = engine.design(spec)
    assert result.theme.key == "client"
    assert result.selection.included
    assert result.document.key == "demo-report"
    assert result.plan.total_pages >= 2
    assert result.entries
    assert result.manifest["theme_digest"]
    assert result.design_digest == result.design_digest
    assert len(result.outputs) == 4
    assert {output.format for output in result.outputs} == {HTML, MARKDOWN, JSON, PRINT}
    assert result.output(HTML) is not None
    assert result.output("pdf") is None
    assert "pages" in result.as_dict()["pagination"]
    assert result.document.all_sections[0].kind is SectionKind.COVER
    assert result.document.all_sections[1].kind is SectionKind.TOC
    assert any(node.kind is SectionKind.APPENDIX for node in result.document.all_sections)


def test_design_is_deterministic(spec: DesignSpec) -> None:
    first = default_engine().design(spec)
    second = default_engine().design(spec)
    assert first.design_digest == second.design_digest
    assert first.plan.digest() == second.plan.digest()
    for left, right in zip(first.outputs, second.outputs, strict=True):
        assert left.content == right.content
    reordered = replace(spec, findings=tuple(reversed(spec.findings)))
    third = default_engine().design(reordered)
    assert first.document.fingerprint() == third.document.fingerprint()
    assert first.output(HTML).content == third.output(HTML).content  # type: ignore[union-attr]


def test_theme_changes_only_presentation(spec: DesignSpec) -> None:
    client = default_engine().design(spec)
    technical = default_engine().design(replace(spec, theme="technical"))
    assert client.theme.key == "client"
    assert technical.theme.key == "technical"
    assert client.manifest["theme_digest"] != technical.manifest["theme_digest"]
    assert [node.title for node in client.document.sections] == [
        node.title for node in technical.document.sections
    ]
    assert client.document.all_findings[0].summary == technical.document.all_findings[0].summary
    assert client.output(JSON).content != technical.output(JSON).content  # type: ignore[union-attr]
    assert "font-family" in technical.output(PRINT).content  # type: ignore[union-attr]


def test_design_options(spec: DesignSpec, engine: ReportDesignerEngine) -> None:
    minimal = replace(
        spec,
        options={"cover": False, "toc": False, "appendix": False, "findings_section": False},
    )
    result = engine.design(minimal)
    kinds = {node.kind for node in result.document.all_sections}
    assert SectionKind.COVER not in kinds
    assert SectionKind.TOC not in kinds
    assert SectionKind.APPENDIX not in kinds
    assert SectionKind.FINDINGS not in kinds
    assert result.entries == ()
    assert result.plan.total_pages >= 1


def test_render_one_and_manifest(spec: DesignSpec, engine: ReportDesignerEngine) -> None:
    html = engine.render_one(spec, HTML)
    assert html.format == HTML
    manifest = engine.manifest_for(spec)
    assert manifest["design_digest"]
    assert manifest["formats"] == [JSON]
    with pytest.raises(ValueError):
        engine.design(replace(spec, formats=("pdf",)))  # type: ignore[arg-type]


def test_engine_fallbacks(spec: DesignSpec, engine: ReportDesignerEngine) -> None:
    fallback = engine.design(replace(spec, theme="missing-theme"))
    assert fallback.theme.key == "client"
    empty_engine = ReportDesignerEngine()
    with pytest.raises(ValueError):
        empty_engine.design(spec)
    custom_themes = ThemeRegistry((engine.themes.get("print"),))
    custom = default_engine(themes=custom_themes).design(spec)
    assert custom.theme.key == "print"


def sample_payload() -> dict[str, object]:
    return {
        "key": "payload-report",
        "title": "Payload Report",
        "client": "Acme",
        "generated_at": "2026-02-01",
        "theme": "technical",
        "findings": [
            {
                "value": "f-1",
                "label": "Finding one",
                "title": "Finding one",
                "severity": "high",
                "status": "confirmed",
                "tags": ["web"],
                "confidence": 0.8,
                "evidence": [
                    {"value": "e-1", "title": "Log", "content": "secret", "sensitive": True}
                ],
            }
        ],
        "sections": [
            {
                "key": "intro",
                "title": "Introduction",
                "kind": "text",
                "body": "Body text",
                "children": [{"key": "detail", "title": "Detail", "level": 2}],
            }
        ],
        "rules": [
            {"name": "drop-secret", "action": "exclude", "tags": ["secret"]},
            {"name": "all", "action": "include"},
        ],
        "redactions": [
            {"name": "email", "pattern": "[A-Z0-9._%+-]+@[A-Z0-9.-]+", "replacement": "[EMAIL]"}
        ],
        "minimum_severity": "low",
        "formats": ["html", "json"],
        "options": {"cover": True, "toc": True},
    }


def test_spec_from_dict() -> None:
    parsed = spec_from_dict(sample_payload())
    assert parsed.key == "payload-report"
    assert parsed.theme == "technical"
    assert len(parsed.findings) == 1
    assert parsed.findings[0].ref == EntityRef.of("finding", "f-1", "Finding one")
    assert parsed.findings[0].evidence[0].sensitive is True
    assert parsed.sections[0].children[0].key == "detail"
    assert parsed.rules[0].name == "drop-secret"
    assert parsed.redactions[0].replacement == "[EMAIL]"
    assert parsed.formats == (HTML, JSON)
    assert parsed.options["cover"] is True
    result = default_engine().design(parsed)
    assert result.output(HTML) is not None
    assert result.output(JSON) is not None
    assert result.output(MARKDOWN) is None


def test_spec_from_dict_defaults() -> None:
    parsed = spec_from_dict({"title": "No Key"})
    assert parsed.key == design_key("No Key")
    assert parsed.classification == "internal"
    assert parsed.formats == (HTML, MARKDOWN, JSON, PRINT)
    assert parsed.sections == ()
    assert parsed.findings == ()


def test_dto_validation_errors() -> None:
    with pytest.raises(V3Error):
        spec_from_dict({})
    with pytest.raises(V3Error):
        spec_from_dict({"title": ""})
    with pytest.raises(V3Error):
        spec_from_dict({"title": "x", "sections": [{"title": "missing key"}]})
    with pytest.raises(V3Error):
        spec_from_dict({"title": "x", "formats": [123]})
    with pytest.raises(V3Error):
        parse_finding({"value": "x", "title": "X", "severity": "catastrophic"})
    with pytest.raises(V3Error):
        parse_format({"format": ""})
    with pytest.raises(V3Error):
        spec_from_dict({"title": "x", "sections": [{"key": "a", "title": "A", "kind": "bad"}]})


def test_design_with_authored_finding_and_section() -> None:
    finding = parse_finding({"value": "f-1", "title": "Issue", "severity": "medium"})
    section = LayoutSection(key="notes", title="Notes", findings=(finding,))
    spec = DesignSpec(key="x", title="X", sections=(section,))
    result = default_engine().design(spec)
    assert result.selection.total == 0
    assert result.document.finding_count == 1
    assert result.document.severity.medium == 1
