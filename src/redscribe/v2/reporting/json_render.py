"""JSON renderer and stable document envelopes for reporting output."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.reporting.identifiers import canonical_json
from redscribe.v2.reporting.models import RenderedReport, ReportDocument
from redscribe.v2.reporting.severity import severity_summary


def document_envelope(
    document: ReportDocument,
    *,
    manifest: Mapping[str, Any] | None = None,
    compact: bool = True,
) -> dict[str, Any]:
    """Build the JSON structure emitted by the JSON renderer."""
    payload: dict[str, Any] = {
        "schema": "redscribe.report/v1",
        "title": document.title,
        "template": document.template,
        "generated_at": document.generated_at,
        "identifier": document.identifier,
        "severity": severity_summary(document.severity),
        "config": document.config.as_dict(),
        "sections": [section.as_dict() for section in document.sections],
        "findings": [finding.as_dict() for finding in document.findings],
        "source_digest": document.source_digest,
        "warnings": list(document.warnings),
    }
    if compact:
        payload["summary"] = {
            "finding_count": document.finding_count,
            "section_count": len(document.all_sections()),
            "evidence_count": sum(len(item.evidence) for item in document.findings),
        }
    if manifest is not None:
        payload["manifest"] = dict(manifest)
    return payload


def render_json(
    document: ReportDocument,
    *,
    manifest: Mapping[str, Any] | None = None,
    pretty: bool = False,
) -> str:
    """Render a report document as canonical JSON."""
    payload = document_envelope(document, manifest=manifest)
    if pretty:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    return canonical_json(payload)


def render_json_bytes(document: ReportDocument, *, pretty: bool = False) -> bytes:
    """Render a report document as UTF-8 JSON bytes."""
    return render_json(document, pretty=pretty).encode("utf-8")


def json_report_response(
    rendered: RenderedReport,
    *,
    status: int = 200,
) -> dict[str, Any]:
    """Wrap a rendered JSON report for an API response."""
    return {
        "status": status,
        "filename": rendered.filename,
        "mime": rendered.mime,
        "content": rendered.content,
        "manifest": dict(rendered.manifest),
    }


def render_finding_list(findings: Sequence[object]) -> str:
    """Render a simple JSON list of as_dict objects."""
    values = [item.as_dict() for item in findings if hasattr(item, "as_dict")]
    return canonical_json(values)


def merge_json_documents(documents: Sequence[ReportDocument]) -> dict[str, Any]:
    """Merge several report documents into one JSON envelope."""
    return {
        "schema": "redscribe.report-bundle/v1",
        "count": len(documents),
        "reports": [document_envelope(document) for document in documents],
    }


def json_lines(documents: Sequence[ReportDocument]) -> str:
    """Render report documents as newline-delimited JSON."""
    return "\n".join(canonical_json(document_envelope(item)) for item in documents) + "\n"


def parse_json_report(raw: str) -> dict[str, Any]:
    """Parse a JSON report payload, validating its root shape."""
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("JSON report must be an object")
    if value.get("schema") not in (None, "redscribe.report/v1"):
        raise ValueError(f"Unknown report schema: {value.get('schema')}")
    return value
