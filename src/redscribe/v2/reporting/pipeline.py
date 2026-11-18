"""End-to-end report build, render, validate, and export pipelines."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.reporting.evidence import (
    evidence_stats,
    with_excerpts,
)
from redscribe.v2.reporting.html_render import render_html, render_print_html
from redscribe.v2.reporting.identifiers import digest_text, slugify
from redscribe.v2.reporting.inclusion import (
    apply_inclusion,
    confidence_for,
    rule_summary,
    rules_for_config,
    sort_selected,
)
from redscribe.v2.reporting.inclusion import (
    rule_digest as inclusion_digest,
)
from redscribe.v2.reporting.manifest import (
    reproducibility_manifest,
    source_fallback,
)
from redscribe.v2.reporting.markdown_render import render_markdown
from redscribe.v2.reporting.models import (
    REPORT_FORMATS,
    EvidenceRef,
    Finding,
    FindingStatus,
    RenderedReport,
    ReportConfig,
    ReportDocument,
    ReportSection,
    SeverityCounts,
    SourceNote,
    ValidationIssue,
)
from redscribe.v2.reporting.print_layout import (
    get_print_profile,
    override_profile,
    profile_digest,
)
from redscribe.v2.reporting.redaction import (
    builtin_redactions,
)
from redscribe.v2.reporting.redaction import (
    rule_digest as redaction_digest,
)
from redscribe.v2.reporting.sections import (
    clone_section_tree,
    findings_in_sections,
    insert_section,
    renumber_sections,
)
from redscribe.v2.reporting.serialization import parse_config, parse_format
from redscribe.v2.reporting.severity import count_severities, severity_summary, sort_findings
from redscribe.v2.reporting.source import build_source
from redscribe.v2.reporting.templates import clone_template_sections, get_template, template_digest
from redscribe.v2.reporting.validation import (
    has_errors,
    issues_as_dicts,
    validate_config,
    validate_format,
)

FORMAT_EXTENSIONS: dict[str, str] = {
    "markdown": ".md",
    "html": ".html",
    "json": ".json",
    "print": ".print.html",
}
FORMAT_MIMES: dict[str, str] = {
    "markdown": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "print": "text/html; charset=utf-8",
}


class ReportingService:
    """Coordinate reporting operations against one vault."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault

    @property
    def vault(self) -> Vault:
        return self._vault

    def source(self, generated_at: str = "", **filters: object) -> dict[str, object]:
        """Return a deterministic source snapshot payload."""
        tag = str(filters.get("tag", ""))
        status = str(filters.get("status", ""))
        root_raw = filters.get("root_id")
        root_id = root_raw if isinstance(root_raw, int) and not isinstance(root_raw, bool) else None
        snapshot = build_source(
            self._vault,
            tag=tag,
            status=status,
            root_id=root_id,
            generated_at=generated_at,
        )
        return snapshot.as_dict()

    def templates(self) -> tuple[dict[str, object], ...]:
        """Return all template summaries."""
        from redscribe.v2.reporting.templates import template_summaries

        return template_summaries()

    def template(self, key: str) -> dict[str, object]:
        """Return one full template definition."""
        return get_template(key).as_dict()

    def config(self, payload: dict[str, object], *, generated_at: str = "") -> ReportConfig:
        """Parse and augment a configuration payload."""
        config = parse_config(payload)
        if not config.generated_at and generated_at:
            config = replace(config, generated_at=generated_at)
        if not config.sections:
            config = replace(config, sections=clone_template_sections(config.template))
        return config

    def build(
        self,
        payload: dict[str, object],
        *,
        generated_at: str = "",
        include_source: bool = True,
    ) -> ReportDocument:
        """Build a report document from a configuration payload."""
        config = self.config(payload, generated_at=generated_at)
        snapshot = build_source(self._vault, generated_at=config.generated_at)
        selected = sort_selected(apply_inclusion(snapshot.notes, config))
        findings = self._findings_from_notes(selected, config)
        sections = self._sections_for(config, findings)
        section_findings = findings_in_sections(sections)
        all_findings = section_findings or findings
        counts = count_severities(all_findings)
        warnings: list[str] = []
        if not all_findings:
            warnings.append("No findings matched the current inclusion rules.")
        if any(item.sensitive for finding in all_findings for item in finding.evidence):
            warnings.append("Sensitive evidence was included and redaction rules were applied.")
        source_digest = snapshot.digest() if include_source else ""
        return ReportDocument(
            config=config,
            sections=sections,
            findings=all_findings,
            severity=counts,
            title=config.title,
            template=config.template,
            generated_at=config.generated_at,
            source_digest=source_digest,
            warnings=tuple(warnings),
        )

    def _findings_from_notes(
        self, notes: tuple[SourceNote, ...], config: ReportConfig
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for note in notes:
            evidence: EvidenceRef = note.evidence
            summary = _first_paragraph(note.content)
            findings.append(
                Finding(
                    identifier=f"note-{note.identifier}",
                    title=note.title,
                    summary=summary,
                    severity=note.severity,
                    status=_finding_status(note.status),
                    category=note.category,
                    tags=note.tags,
                    evidence=(evidence,),
                    recommendation=_recommendation(note.severity),
                    references=tuple(value for value in (note.target, note.flag) if value),
                    confidence=confidence_for(note),
                    affected=note.target,
                )
            )
        result = sort_findings(findings)
        redactions = config.redactions or builtin_redactions(include_hosts=config.redact_sensitive)
        return tuple(
            with_excerpts(_redact_finding(item, redactions, config.redact_sensitive))
            for item in result
        )

    def _sections_for(
        self, config: ReportConfig, findings: tuple[Finding, ...]
    ) -> tuple[ReportSection, ...]:
        sections = clone_section_tree(config.sections)
        buckets: dict[str, list[Finding]] = {}
        for finding in findings:
            key = finding.category or "findings"
            buckets.setdefault(key, []).append(finding)
        result: list[Any] = []
        attached: set[str] = set()
        for section in sections:
            updated = section
            for candidate in section.walk():
                if candidate.kind != "findings" or candidate.identifier in attached:
                    continue
                assigned = buckets.get(candidate.identifier, [])
                if not assigned:
                    assigned = [item for item in findings if item.identifier not in attached]
                if not assigned:
                    continue
                attached.update(item.identifier for item in assigned)
                updated = _attach_findings(updated, candidate.identifier, tuple(assigned))
            result.append(updated)
        unattached = [item for item in findings if item.identifier not in attached]
        if unattached:
            result = list(
                insert_section(
                    tuple(result),
                    _findings_section(unattached),
                    index=len(result),
                )
            )
        return renumber_sections(tuple(result))

    def validate(self, payload: dict[str, object], *, generated_at: str = "") -> dict[str, object]:
        """Validate a configuration payload."""
        config = self.config(payload, generated_at=generated_at)
        issues = validate_config(config)
        return {
            "valid": not has_errors(issues),
            "errors": len([issue for issue in issues if issue.severity == "error"]),
            "warnings": len([issue for issue in issues if issue.severity == "warning"]),
            "issues": issues_as_dicts(issues),
        }

    def render(
        self,
        payload: dict[str, object],
        fmt: str,
        *,
        generated_at: str = "",
        profile: str = "",
    ) -> RenderedReport:
        """Build and render a report in one call."""
        document = self.build(payload, generated_at=generated_at)
        return self.render_document(document, fmt, profile=profile)

    def render_document(
        self, document: ReportDocument, fmt: str, *, profile: str = ""
    ) -> RenderedReport:
        """Render a built document into one output format."""
        normalized = validate_format(fmt)
        content = self._content(document, normalized, profile)
        filename = f"{document.identifier}{FORMAT_EXTENSIONS[normalized]}"
        rendered = RenderedReport(
            format=normalized,  # type: ignore[arg-type]
            content=content,
            filename=filename,
            mime=FORMAT_MIMES[normalized],
        )
        manifest = self.manifest(document, rendered, profile=profile)
        return replace(rendered, manifest=manifest)

    def _content(self, document: ReportDocument, fmt: str, profile: str) -> str:
        if fmt == "markdown":
            return render_markdown(document)
        if fmt == "html":
            return render_html(document, profile=self._profile(document, profile))
        if fmt == "print":
            return render_print_html(document)
        import json

        manifest = self.manifest(document, None, profile=profile)
        return json.dumps(
            {"report": document.as_dict(), "manifest": manifest},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _profile(self, document: ReportDocument, profile: str) -> Any:
        selected = get_print_profile(profile or document.config.print_profile)
        return override_profile(
            selected,
            page_size=document.config.page_size,
            orientation=document.config.orientation,
            show_cover=document.config.print_cover,
            show_toc=document.config.print_toc,
        )

    def manifest(
        self, document: ReportDocument, rendered: RenderedReport | None, *, profile: str = ""
    ) -> dict[str, Any]:
        """Build the reproducibility manifest for a report."""
        print_profile = self._profile(document, profile)
        return reproducibility_manifest(
            document,
            rendered=rendered,
            template_digest=template_digest(document.template),
            rules_digest=inclusion_digest(document.config.rules),
            redaction_digest=redaction_digest(document.config.redactions),
            print_digest=profile_digest(print_profile),
        )

    def export(
        self,
        payload: dict[str, object],
        fmt: str,
        *,
        generated_at: str = "",
        profile: str = "",
        directory: str | Path | None = None,
    ) -> dict[str, object]:
        """Render a report and optionally write it to disk."""
        document = self.build(payload, generated_at=generated_at)
        rendered = self.render_document(document, fmt, profile=profile)
        result = {
            "format": rendered.format,
            "filename": rendered.filename,
            "mime": rendered.mime,
            "content": rendered.content,
            "manifest": rendered.manifest,
            "bytes": len(rendered.content.encode("utf-8")),
        }
        if directory is not None:
            path = Path(directory) / rendered.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered.content, encoding="utf-8", newline="\n")
            result["path"] = str(path)
        return result

    def bundle(
        self,
        payload: dict[str, object],
        *,
        generated_at: str = "",
        directory: str | Path,
        formats: tuple[str, ...] = ("markdown", "html", "json"),
    ) -> dict[str, object]:
        """Export several formats plus a manifest to one directory."""
        document = self.build(payload, generated_at=generated_at)
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, object] = {}
        for fmt in formats:
            rendered = self.render_document(document, fmt)
            (target / rendered.filename).write_text(
                rendered.content, encoding="utf-8", newline="\n"
            )
            outputs[fmt] = {
                "filename": rendered.filename,
                "bytes": len(rendered.content.encode("utf-8")),
                "sha256": digest_text(rendered.content),
            }
        manifest = self.manifest(document, None)
        manifest["outputs"] = outputs
        manifest["digest"] = digest_text(
            __import__("json").dumps(manifest, ensure_ascii=False, sort_keys=True)
        )
        (target / "manifest.json").write_text(
            __import__("json").dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        return {
            "directory": str(target),
            "formats": list(formats),
            "outputs": outputs,
            "manifest": manifest,
        }

    def preview(self, payload: dict[str, object], *, generated_at: str = "") -> dict[str, object]:
        """Return a lightweight preview payload for the builder UI."""
        document = self.build(payload, generated_at=generated_at)
        return {
            "title": document.title,
            "template": document.template,
            "finding_count": document.finding_count,
            "severity": severity_summary(document.severity),
            "sections": [
                {
                    "identifier": section.identifier,
                    "title": section.title,
                    "level": section.level,
                    "finding_count": section.finding_count,
                }
                for section in document.all_sections()
            ],
            "warnings": list(document.warnings),
            "evidence": evidence_stats(document.findings),
        }

    def severity(self, payload: dict[str, object], *, generated_at: str = "") -> dict[str, object]:
        """Return severity analytics for a configuration."""
        document = self.build(payload, generated_at=generated_at)
        return {
            **severity_summary(document.severity),
            "findings": [
                {
                    "identifier": finding.identifier,
                    "severity": finding.severity,
                    "title": finding.title,
                }
                for finding in document.findings
            ],
        }

    def inclusion_report(
        self, payload: dict[str, object], *, generated_at: str = ""
    ) -> dict[str, object]:
        """Return inclusion rule analytics for a configuration."""
        config = self.config(payload, generated_at=generated_at)
        snapshot = build_source(self._vault, generated_at=config.generated_at)
        selected = sort_selected(apply_inclusion(snapshot.notes, config))
        return {
            "source_notes": len(snapshot.notes),
            "selected_notes": len(selected),
            "excluded_notes": len(snapshot.notes) - len(selected),
            "rules": rule_summary(rules_for_config(config)),
            "severity": count_severities(_notes_as_findings(selected)).as_dict(),
        }


def build_report(
    vault: Vault, payload: dict[str, object], *, generated_at: str = ""
) -> ReportDocument:
    """Build a report document with a service instance."""
    return ReportingService(vault).build(payload, generated_at=generated_at)


def export_report(
    vault: Vault,
    payload: dict[str, object],
    fmt: str,
    *,
    generated_at: str = "",
    profile: str = "",
    directory: str | Path | None = None,
) -> dict[str, object]:
    """Export a report with a service instance."""
    return ReportingService(vault).export(
        payload, fmt, generated_at=generated_at, profile=profile, directory=directory
    )


def render_report(
    vault: Vault,
    payload: dict[str, object],
    fmt: str,
    *,
    generated_at: str = "",
    profile: str = "",
) -> RenderedReport:
    """Render a report with a service instance."""
    return ReportingService(vault).render(payload, fmt, generated_at=generated_at, profile=profile)


def _first_paragraph(content: str) -> str:
    chunks: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "```", "|")):
            if chunks:
                break
            continue
        chunks.append(stripped)
        if len(" ".join(chunks)) > 240:
            break
    return " ".join(chunks)[:280].strip()


def _finding_status(status: str) -> FindingStatus:
    mapping: dict[str, FindingStatus] = {
        "todo": "open",
        "active": "confirmed",
        "done": "mitigated",
        "blocked": "open",
    }
    return mapping.get(status, "open")


def _recommendation(severity: str) -> str:
    return {
        "critical": "Remediate immediately and validate the fix with a retest.",
        "high": "Prioritize remediation in the current work cycle.",
        "medium": "Schedule remediation and document compensating controls.",
        "low": "Track for routine remediation.",
        "info": "No direct remediation required; retain as context.",
    }.get(severity, "Review and track this observation.")


def _redact_finding(finding: Finding, rules: tuple[Any, ...], enabled: bool) -> Finding:
    if not enabled:
        return finding
    from redscribe.v2.reporting.redaction import redact_finding as apply

    return apply(finding, rules)


def _attach_findings(section: Any, identifier: str, findings: tuple[Finding, ...]) -> Any:
    if section.identifier == identifier:
        return replace(section, findings=dedup_findings((*section.findings, *findings)))
    from redscribe.v2.reporting.models import ReportSection

    if not isinstance(section, ReportSection):
        return section
    return replace(
        section,
        children=tuple(_attach_findings(child, identifier, findings) for child in section.children),
    )


def dedup_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """Remove duplicate findings by identifier, keeping first occurrence."""
    seen: set[str] = set()
    result: list[Finding] = []
    for finding in findings:
        if finding.identifier in seen:
            continue
        seen.add(finding.identifier)
        result.append(finding)
    return tuple(result)


def _findings_section(findings: list[Finding]) -> Any:
    from redscribe.v2.reporting.models import ReportSection

    return ReportSection(
        identifier="additional-findings",
        title="Additional Findings",
        kind="findings",
        findings=tuple(findings),
    )


def _notes_as_findings(notes: tuple[SourceNote, ...]) -> tuple[Finding, ...]:
    return tuple(
        Finding(identifier=f"note-{note.identifier}", title=note.title, severity=note.severity)
        for note in notes
    )


def format_options() -> dict[str, object]:
    """Return the supported export formats and their metadata."""
    return {
        "formats": list(REPORT_FORMATS),
        "extensions": dict(FORMAT_EXTENSIONS),
        "mimes": dict(FORMAT_MIMES),
    }


def normalize_format(value: str) -> str:
    """Normalize a format value used by API handlers."""
    return parse_format(value)


def validation_summary(issues: tuple[ValidationIssue, ...]) -> dict[str, object]:
    """Summarize validation issues for API responses."""
    return {
        "valid": not has_errors(issues),
        "issues": issues_as_dicts(issues),
    }


def clone_config(config: ReportConfig) -> ReportConfig:
    """Return a deep-ish copy of a configuration with cloned sections."""
    return replace(config, sections=clone_section_tree(config.sections))


def severity_counts_for(document: ReportDocument) -> SeverityCounts:
    """Return the severity counts attached to a document."""
    return document.severity


def document_slug(document: ReportDocument) -> str:
    """Return the stable filename slug for a document."""
    return slugify(document.title)


def document_digest(document: ReportDocument) -> str:
    """Return the source digest or compute one for a document."""
    return document.source_digest or source_fallback(document)
