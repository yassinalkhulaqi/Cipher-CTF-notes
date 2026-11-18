"""Reporting studio: deterministic security report construction and export."""

from __future__ import annotations

from redscribe.v2.reporting.evidence import evidence_from_note, excerpt
from redscribe.v2.reporting.html_render import render_html, render_print_html
from redscribe.v2.reporting.json_render import render_json
from redscribe.v2.reporting.manifest import reproducibility_manifest
from redscribe.v2.reporting.markdown_render import render_markdown
from redscribe.v2.reporting.models import (
    EVIDENCE_KINDS,
    FINDING_STATUSES,
    REPORT_FORMATS,
    SEVERITY_ORDER,
    EvidenceRef,
    Finding,
    InclusionRule,
    RedactionRule,
    RenderedReport,
    ReportConfig,
    ReportDocument,
    ReportSection,
    ReportTemplate,
    Severity,
    SeverityCounts,
    SourceNote,
    ValidationIssue,
)
from redscribe.v2.reporting.pipeline import (
    FORMAT_EXTENSIONS,
    FORMAT_MIMES,
    ReportingService,
    build_report,
    export_report,
    render_report,
)
from redscribe.v2.reporting.print_layout import PrintProfile, get_print_profile, profile_names
from redscribe.v2.reporting.redaction import builtin_redactions, redact_text
from redscribe.v2.reporting.serialization import parse_config
from redscribe.v2.reporting.severity import count_severities, severity_summary
from redscribe.v2.reporting.source import build_source
from redscribe.v2.reporting.templates import TEMPLATES, get_template, template_keys
from redscribe.v2.reporting.validation import validate_config

__all__ = [
    "EVIDENCE_KINDS",
    "FINDING_STATUSES",
    "FORMAT_EXTENSIONS",
    "FORMAT_MIMES",
    "REPORT_FORMATS",
    "SEVERITY_ORDER",
    "TEMPLATES",
    "EvidenceRef",
    "Finding",
    "InclusionRule",
    "PrintProfile",
    "RedactionRule",
    "RenderedReport",
    "ReportConfig",
    "ReportDocument",
    "ReportSection",
    "ReportTemplate",
    "ReportingService",
    "Severity",
    "SeverityCounts",
    "SourceNote",
    "ValidationIssue",
    "build_report",
    "build_source",
    "builtin_redactions",
    "count_severities",
    "evidence_from_note",
    "excerpt",
    "export_report",
    "get_print_profile",
    "get_template",
    "parse_config",
    "profile_names",
    "redact_text",
    "render_html",
    "render_json",
    "render_markdown",
    "render_print_html",
    "render_report",
    "reproducibility_manifest",
    "severity_summary",
    "template_keys",
    "validate_config",
]
