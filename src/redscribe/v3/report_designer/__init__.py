"""Visual, deterministic report designer for RedScribe V3.

The package turns a design specification into a fully paginated layout document
and renders it to HTML, Markdown, canonical JSON, and print CSS. It reuses the
V3 entity contracts for identity and stays entirely local and offline.
"""

from __future__ import annotations

from redscribe.v3.report_designer.builders import (
    AppendixBuilder,
    CoverBuilder,
    TocBuilder,
    TocEntry,
    build_back_matter,
    build_front_matter,
)
from redscribe.v3.report_designer.dto import spec_from_dict
from redscribe.v3.report_designer.engine import (
    DesignResult,
    DesignSpec,
    ReportDesignerEngine,
    default_engine,
    design_key,
)
from redscribe.v3.report_designer.identifiers import (
    anchor_for,
    canonical_json,
    digest,
    page_anchor,
    page_label,
    slugify,
)
from redscribe.v3.report_designer.model import (
    EVIDENCE_KINDS,
    FINDING_STATUSES,
    REDACTION_SCOPES,
    SEVERITY_ORDER,
    EvidenceItem,
    FindingItem,
    LayoutDocument,
    LayoutSection,
    RedactionRule,
    SectionKind,
    SelectionRule,
    Severity,
    SeverityCounts,
    count_severities,
)
from redscribe.v3.report_designer.pagination import (
    Page,
    PageItem,
    PaginationEngine,
    PaginationPlan,
    default_paginator,
    estimate_section_lines,
)
from redscribe.v3.report_designer.redaction import (
    RedactionPreview,
    RedactionSpan,
    apply_redactions,
    builtin_redactions,
    preview_document,
    redact_text,
    verify_redactions,
)
from redscribe.v3.report_designer.renderers import (
    RENDER_FORMATS,
    RenderContext,
    RendererRegistry,
    RenderFormat,
    RenderOutput,
    default_registry,
)
from redscribe.v3.report_designer.selection import (
    FindingDecision,
    SelectionPolicy,
    SelectionResult,
    default_policy,
    stable_sort_findings,
)
from redscribe.v3.report_designer.themes import (
    ReportTheme,
    ThemeRegistry,
    ThemeTokens,
    builtin_themes,
    default_theme_registry,
)

__all__ = [
    "EVIDENCE_KINDS",
    "FINDING_STATUSES",
    "REDACTION_SCOPES",
    "RENDER_FORMATS",
    "SEVERITY_ORDER",
    "AppendixBuilder",
    "CoverBuilder",
    "DesignResult",
    "DesignSpec",
    "EvidenceItem",
    "FindingDecision",
    "FindingItem",
    "LayoutDocument",
    "LayoutSection",
    "Page",
    "PageItem",
    "PaginationEngine",
    "PaginationPlan",
    "RedactionPreview",
    "RedactionRule",
    "RedactionSpan",
    "RenderContext",
    "RenderFormat",
    "RenderOutput",
    "RendererRegistry",
    "ReportDesignerEngine",
    "ReportTheme",
    "SectionKind",
    "SelectionPolicy",
    "SelectionResult",
    "SelectionRule",
    "Severity",
    "SeverityCounts",
    "ThemeRegistry",
    "ThemeTokens",
    "TocBuilder",
    "TocEntry",
    "anchor_for",
    "apply_redactions",
    "build_back_matter",
    "build_front_matter",
    "builtin_redactions",
    "builtin_themes",
    "canonical_json",
    "count_severities",
    "default_engine",
    "default_paginator",
    "default_policy",
    "default_registry",
    "default_theme_registry",
    "design_key",
    "digest",
    "estimate_section_lines",
    "page_anchor",
    "page_label",
    "preview_document",
    "redact_text",
    "slugify",
    "spec_from_dict",
    "stable_sort_findings",
    "verify_redactions",
]
