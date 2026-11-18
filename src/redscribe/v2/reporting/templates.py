"""Built-in report templates and template registry operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from redscribe.v2.reporting.models import ReportSection, ReportTemplate
from redscribe.v2.reporting.sections import renumber_sections


def _section(
    identifier: str,
    title: str,
    kind: str = "text",
    body: str = "",
    children: tuple[ReportSection, ...] = (),
    **values: Any,
) -> ReportSection:
    return ReportSection(
        identifier=identifier,
        title=title,
        kind=kind,
        body=body,
        children=children,
        **values,
    )


_ENGAGEMENT = ReportTemplate(
    key="engagement",
    name="Engagement Report",
    description="Full security assessment with findings, evidence, and remediation.",
    default_title="Security Engagement Report",
    classification="confidential",
    tags=("report", "engagement"),
    print_profile="standard",
    glyph="◇",
    sections=renumber_sections(
        (
            _section(
                "executive-summary",
                "Executive Summary",
                body="Summarize the engagement outcome for leadership.",
            ),
            _section(
                "scope-and-method",
                "Scope and Methodology",
                children=(
                    _section("scope", "Scope"),
                    _section("methodology", "Methodology"),
                ),
            ),
            _section("findings", "Findings", kind="findings"),
            _section(
                "remediation",
                "Remediation Plan",
                body="Prioritize fixes by severity and effort.",
            ),
            _section(
                "appendices",
                "Appendices",
                kind="appendix",
                children=(
                    _section("evidence-index", "Evidence Index", kind="evidence"),
                    _section("severity-summary", "Severity Summary", kind="severity"),
                ),
            ),
        )
    ),
)

_PENTEST = ReportTemplate(
    key="pentest",
    name="Penetration Test",
    description="Technical penetration test report organized by attack phase.",
    default_title="Penetration Test Report",
    classification="restricted",
    tags=("report", "pentest"),
    print_profile="technical",
    glyph="⌁",
    sections=renumber_sections(
        (
            _section("overview", "Overview"),
            _section("reconnaissance", "Reconnaissance", kind="findings"),
            _section("initial-access", "Initial Access", kind="findings"),
            _section("lateral-movement", "Lateral Movement", kind="findings"),
            _section("impact", "Impact", kind="findings"),
            _section("recommendations", "Recommendations"),
            _section(
                "appendices",
                "Appendices",
                kind="appendix",
                children=(
                    _section("commands", "Command Log", kind="evidence"),
                    _section("artifacts", "Artifacts", kind="evidence"),
                ),
            ),
        )
    ),
)

_CTF = ReportTemplate(
    key="ctf",
    name="CTF Writeup",
    description="Challenge writeup with solve path, flags, and supporting artifacts.",
    default_title="CTF Challenge Writeup",
    classification="public",
    tags=("report", "ctf"),
    print_profile="compact",
    glyph="⚑",
    sections=renumber_sections(
        (
            _section("challenge", "Challenge Overview"),
            _section("recon", "Reconnaissance", kind="findings"),
            _section("exploitation", "Exploitation", kind="findings"),
            _section("flag", "Flag", kind="text"),
            _section("reflection", "Reflection"),
            _section("artifacts", "Artifacts", kind="appendix"),
        )
    ),
)

_INCIDENT = ReportTemplate(
    key="incident",
    name="Incident Report",
    description="Timeline-driven incident response report with containment actions.",
    default_title="Security Incident Report",
    classification="confidential",
    tags=("report", "incident"),
    print_profile="standard",
    glyph="△",
    sections=renumber_sections(
        (
            _section("summary", "Incident Summary"),
            _section("timeline", "Timeline", kind="findings"),
            _section("root-cause", "Root Cause"),
            _section("containment", "Containment", kind="findings"),
            _section("lessons", "Lessons Learned"),
            _section("appendices", "Appendices", kind="appendix"),
        )
    ),
)

_EXECUTIVE = ReportTemplate(
    key="executive",
    name="Executive Brief",
    description="Short leadership brief with risk posture and key decisions.",
    default_title="Executive Security Brief",
    classification="confidential",
    tags=("report", "executive"),
    print_profile="compact",
    glyph="◆",
    sections=renumber_sections(
        (
            _section("headline", "Headline"),
            _section("risk-posture", "Risk Posture", kind="severity"),
            _section("key-findings", "Key Findings", kind="findings"),
            _section("decisions", "Decisions Needed"),
            _section("next-steps", "Next Steps"),
        )
    ),
)

TEMPLATES: tuple[ReportTemplate, ...] = (
    _ENGAGEMENT,
    _PENTEST,
    _CTF,
    _INCIDENT,
    _EXECUTIVE,
)
TEMPLATE_MAP: dict[str, ReportTemplate] = {template.key: template for template in TEMPLATES}


def get_template(key: str) -> ReportTemplate:
    """Return a template by key or raise ``ValueError``."""
    normalized = key.strip().casefold()
    template = TEMPLATE_MAP.get(normalized)
    if template is None:
        raise ValueError(f"Unknown report template: {key}")
    return template


def template_keys() -> tuple[str, ...]:
    """Return all available template keys."""
    return tuple(template.key for template in TEMPLATES)


def template_summaries() -> tuple[dict[str, object], ...]:
    """Return metadata suitable for template selection cards."""
    return tuple(
        {
            "key": template.key,
            "name": template.name,
            "description": template.description,
            "default_title": template.default_title,
            "classification": template.classification,
            "tags": list(template.tags),
            "print_profile": template.print_profile,
            "glyph": template.glyph,
            "section_count": len(template.section_keys()),
        }
        for template in TEMPLATES
    )


def clone_template_sections(key: str) -> tuple[ReportSection, ...]:
    """Return a defensive copy of a template's section tree."""
    from redscribe.v2.reporting.sections import clone_section_tree

    return clone_section_tree(get_template(key).sections)


def section_kinds(templates: Iterable[ReportTemplate] = TEMPLATES) -> tuple[str, ...]:
    """Return the sorted set of section kinds used by templates."""
    kinds = {
        section.kind
        for template in templates
        for root in template.sections
        for section in root.walk()
    }
    return tuple(sorted(kinds))


def find_template_by_tag(tag: str) -> tuple[ReportTemplate, ...]:
    """Return templates carrying a tag."""
    needle = tag.casefold()
    return tuple(
        template for template in TEMPLATES if needle in {item.casefold() for item in template.tags}
    )


def template_digest(key: str) -> str:
    """Return a stable digest of a template definition."""
    from redscribe.v2.reporting.identifiers import digest

    return digest(get_template(key).as_dict())
