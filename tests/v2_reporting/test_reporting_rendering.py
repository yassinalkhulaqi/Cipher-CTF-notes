from __future__ import annotations

import json

from redscribe.v2.reporting.html_render import (
    esc,
    render_evidence_html,
    render_finding_html,
    render_html,
    render_meta_html,
    render_section_html,
    render_severity_html,
    render_toc_html,
    render_warnings_html,
)
from redscribe.v2.reporting.json_render import (
    document_envelope,
    json_lines,
    json_report_response,
    merge_json_documents,
    parse_json_report,
    render_finding_list,
    render_json,
    render_json_bytes,
)
from redscribe.v2.reporting.manifest import (
    MANIFEST_VERSION,
    manifest_text,
    merge_manifests,
    output_manifest,
    reproducibility_manifest,
    verify_manifest,
)
from redscribe.v2.reporting.markdown_render import (
    bullet_lines,
    escape_cell,
    heading,
    metadata_table,
    render_appendices,
    render_finding_index,
    render_finding_markdown,
    render_markdown,
    render_section_markdown,
    render_toc_markdown,
)
from redscribe.v2.reporting.models import (
    EvidenceRef,
    Finding,
    RenderedReport,
    ReportConfig,
    ReportDocument,
    ReportSection,
    SeverityCounts,
)
from redscribe.v2.reporting.print_layout import (
    build_print_css,
    build_screen_css,
    get_print_profile,
    override_profile,
    paper_label,
    profile_digest,
    profile_names,
    profile_summary,
)


def evidence() -> EvidenceRef:
    return EvidenceRef(
        identifier="ev-1",
        title="Log & output",
        content="$ id\nuid=0(root)",
        kind="command",
        source_path="labs / host",
        locator="line 9",
        excerpt="uid=0(root)",
        sensitive=True,
    )


def finding() -> Finding:
    return Finding(
        identifier="finding-1",
        title="Root access <script>",
        summary="The service ran as root.",
        severity="critical",
        status="confirmed",
        category="web",
        tags=("web", "auth"),
        evidence=(evidence(),),
        impact="Full host compromise.",
        recommendation="Drop privileges.",
        references=("CWE-269", "https://example.test/reference"),
        confidence=0.9,
        cvss="9.8",
        cwe="269",
        affected="app-01",
    )


def sections() -> tuple[ReportSection, ...]:
    section = ReportSection(
        identifier="findings",
        title="Findings",
        kind="findings",
        summary="Confirmed issues",
        body="Body text with | pipe.",
        findings=(finding(),),
        level=2,
        children=(
            ReportSection(
                identifier="details",
                title="Details",
                body="Child body",
                level=3,
                include_toc=False,
            ),
        ),
    )
    return (section,)


def document() -> ReportDocument:
    config = ReportConfig(
        title="Security Review",
        template="engagement",
        client="ACME & Co",
        author="Reporter",
        classification="confidential",
        scope=("web", "host"),
        generated_at="2026-01-01T00:00:00Z",
        introduction="Intro <b>text</b>",
        conclusion="All issues addressed.",
        include_evidence=True,
        include_appendices=True,
        print_toc=True,
        notes="Internal note",
    )
    return ReportDocument(
        config=config,
        sections=sections(),
        findings=(finding(),),
        severity=SeverityCounts(critical=1),
        title="Security Review",
        template="engagement",
        generated_at="2026-01-01T00:00:00Z",
        source_digest="abc123",
        warnings=("Sensitive evidence redacted",),
    )


def test_escape_and_heading_helpers() -> None:
    assert esc('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"
    assert heading("Findings", 9) == "###### Findings"
    assert heading("Findings", 0) == "# Findings"
    assert escape_cell("a|b\nc") == "a\\|b c"
    assert bullet_lines(("one", "", " two ")) == ("- one", "-  two ")


def test_metadata_table_omits_empty_values() -> None:
    table = metadata_table((("Client", "ACME"), ("Author", ""), ("Count", 2)))
    lines = table.splitlines()
    assert lines[0] == "| Field | Value |"
    assert lines[1] == "| --- | --- |"
    assert "| Client | ACME |" in lines
    assert "| Author |  |" not in lines
    assert "| Count | 2 |" in lines


def test_markdown_renderers_include_finding_details() -> None:
    rendered = render_finding_markdown(finding())
    assert "### finding-1: Root access <script>" in rendered
    assert "**Severity:** Critical" in rendered
    assert "### Summary" in rendered
    assert "### Evidence" in rendered
    assert "1. **Log & output**" in rendered
    assert render_finding_markdown(finding(), include_evidence=False).find("### Evidence") == -1


def test_markdown_section_and_toc_renderers() -> None:
    section = sections()[0]
    rendered = render_section_markdown(section)
    assert rendered.startswith("## Findings")
    assert "Body text with | pipe." in rendered
    assert "### Details" in rendered
    assert render_section_markdown(section, include_empty=True).strip() != ""
    toc = render_toc_markdown(document())
    assert "## Contents" in toc
    assert "- Findings" in toc
    assert "- Details" not in toc


def test_markdown_document_renderer_is_complete() -> None:
    text = render_markdown(document(), include_manifest=True)
    assert text.startswith("# Security Review")
    assert "## Introduction" in text
    assert "## Contents" in text
    assert "## Severity Summary" in text
    assert "### finding-1: Root access <script>" in text
    assert "## Conclusion" in text
    assert "## Appendices" in text
    assert "Source digest: `abc123`" in text
    assert "## Notes" in text
    assert "Sensitive evidence redacted" in text


def test_markdown_appendices_and_index() -> None:
    appendices = render_appendices(document())
    assert "### Evidence Index" in appendices
    assert "[1] Log & output" in appendices
    assert "### Severity Summary" in appendices
    index = render_finding_index((finding(),))
    assert "| ID | Finding | Severity | Status |" in index
    assert "finding-1" in index
    assert "Root access <script>" in index


def test_html_helpers_escape_and_structure_output() -> None:
    assert "&lt;script&gt;" in render_finding_html(finding())
    assert 'id="finding-finding-1"' in render_finding_html(finding())
    assert "badge sensitive" in render_evidence_html((evidence(),))
    assert "No evidence recorded." in render_evidence_html(())
    assert "Log &amp; output" in render_evidence_html((evidence(),))
    assert "Meta &amp; Co" not in render_meta_html(document())
    assert "ACME &amp; Co" in render_meta_html(document())
    assert "severity-critical" in render_severity_html(document())
    assert 'href="#section-findings"' in render_toc_html(document())
    assert "Build warnings" in render_warnings_html(document().warnings)
    assert render_warnings_html(()) == ""


def test_html_section_and_document_renderers() -> None:
    section_html = render_section_html(sections()[0])
    assert 'id="section-findings"' in section_html
    assert 'id="section-details"' in section_html
    assert "Body text with | pipe." in section_html
    html = render_html(document(), include_manifest=True)
    assert html.startswith("<!doctype html>")
    assert "<title>Security Review</title>" in html
    assert "REDSCRIBE REPORT" in html
    assert "<style>" in html
    assert 'id="finding-register"' in html
    assert 'id="reproducibility"' in html
    assert "Generated by RedScribe Reporting Studio" in html


def test_print_layout_profiles_and_css() -> None:
    assert "standard" in profile_names()
    assert len(profile_summary()) == len(profile_names())
    assert get_print_profile("landscape").orientation == "landscape"
    assert build_print_css(get_print_profile("standard")).startswith("@page")
    assert "@page" in build_print_css(get_print_profile("standard"))
    assert "print-preview" in build_screen_css(get_print_profile("standard"))
    assert paper_label(get_print_profile("letter")).startswith("LETTER")
    assert profile_digest(get_print_profile("standard")) == profile_digest(
        get_print_profile("standard")
    )
    assert override_profile(get_print_profile("standard"), page_size="letter").page_size == "letter"


def test_print_profile_override_validation() -> None:
    import pytest

    with pytest.raises(ValueError):
        override_profile(get_print_profile("standard"), page_size="tabloid")
    with pytest.raises(ValueError):
        override_profile(get_print_profile("standard"), orientation="diagonal")


def test_json_renderers_and_response_helpers() -> None:
    doc = document()
    payload = document_envelope(doc)
    assert payload["schema"] == "redscribe.report/v1"
    assert payload["summary"]["finding_count"] == 1
    assert payload["summary"]["section_count"] == 2
    assert payload["summary"]["evidence_count"] == 1
    text = render_json(doc)
    assert json.loads(text)["title"] == "Security Review"
    assert "\n  " in render_json(doc, pretty=True)
    assert render_json_bytes(doc).decode("utf-8") == text
    rendered = RenderedReport("json", text, "review.json", "application/json")
    response = json_report_response(rendered, status=201)
    assert response["status"] == 201
    assert response["filename"] == "review.json"
    assert parse_json_report(text)["identifier"] == "security-review"
    assert render_finding_list((finding(),)).startswith("[{")


def test_json_renderer_validation_and_merge() -> None:
    import pytest

    doc = document()
    with pytest.raises(ValueError):
        parse_json_report("[]")
    with pytest.raises(ValueError):
        parse_json_report('{"schema": "other"}')
    bundle = merge_json_documents((doc, doc))
    assert bundle["count"] == 2
    assert len(bundle["reports"]) == 2
    lines = json_lines((doc, doc))
    assert len(lines.splitlines()) == 2
    assert all(json.loads(line)["schema"] == "redscribe.report/v1" for line in lines.splitlines())


def test_manifest_generation_and_verification() -> None:
    doc = document()
    rendered = RenderedReport("markdown", "# Security Review\n", "review.md", "text/markdown")
    manifest = reproducibility_manifest(doc, rendered=rendered)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["report_id"] == "security-review"
    assert manifest["inputs"]["source_digest"] == "abc123"
    assert manifest["outputs"]["markdown"]["filename"] == "review.md"
    assert output_manifest(rendered)["markdown"]["sha256"]
    assert manifest_text(manifest).startswith("Manifest version:")
    verified, actual = verify_manifest(manifest)
    assert verified is True
    assert len(actual) == 64
    assert verify_manifest({"manifest_version": MANIFEST_VERSION})[0] is False


def test_manifest_merge_preserves_outputs_and_warnings() -> None:
    first = output_manifest(RenderedReport("markdown", "body", "review.md", "text/markdown"))
    second = output_manifest(RenderedReport("html", "<p>", "review.html", "text/html"))
    merged = merge_manifests(
        (
            {"manifest_version": MANIFEST_VERSION, "outputs": first, "warnings": ["one"]},
            {"manifest_version": MANIFEST_VERSION, "outputs": second, "warnings": ["two", "one"]},
        )
    )
    assert set(merged["outputs"]) == {"markdown", "html"}
    assert merged["warnings"] == ["one", "two"]
    assert merged["digest"]
