"""Reports namespace routes for the V3 API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.capabilities import CAP_REPORTS
from redscribe.v3.config import default_config
from redscribe.v3.report_designer.dto import parse_format, spec_from_dict
from redscribe.v3.report_designer.engine import DesignResult, DesignSpec, default_engine
from redscribe.v3.report_designer.renderers import EXTENSIONS, MIME_TYPES, RENDER_FORMATS
from redscribe.v3.report_designer.selection import rule_summary

_engine = default_engine()


def _build(spec: DesignSpec) -> DesignResult:
    """Design a spec with minimal rendering, used by inspection routes."""
    return _engine.design(replace(spec, formats=("json",)))


def register(router: V3Router) -> None:
    """Register report designer routes on the supplied router."""

    def health(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "status": "ok",
            "capability": CAP_REPORTS,
            "enabled": default_config.capabilities().has(CAP_REPORTS),
            "formats": list(_engine.renderers.formats()),
            "themes": len(_engine.themes),
        }

    def themes(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "default": _engine.themes.default().key,
            "themes": [theme.as_dict() for theme in _engine.themes.list()],
            "summaries": list(_engine.themes.summaries()),
        }

    def formats(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "formats": list(RENDER_FORMATS),
            "mime_types": dict(MIME_TYPES),
            "extensions": dict(EXTENSIONS),
        }

    def design(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _engine.design(spec_from_dict(body)).as_dict()

    def preview(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        result = _build(spec_from_dict(body))
        return {
            "design_digest": result.design_digest,
            "redaction": result.preview.as_dict(),
            "pagination": {
                "total_pages": result.plan.total_pages,
                "lines_per_page": result.plan.lines_per_page,
                "anchors": dict(result.plan.anchors),
            },
            "toc": [entry.as_dict() for entry in result.entries],
            "selection": {
                "included": [item.key for item in result.selection.included],
                "excluded": [item.key for item in result.selection.excluded],
                "decisions": [item.as_dict() for item in result.selection.decisions],
            },
        }

    def paginate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        result = _build(spec_from_dict(body))
        return {
            "plan": result.plan.as_dict(),
            "entries": [entry.as_dict() for entry in result.entries],
        }

    def render(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        spec = spec_from_dict(body)
        output_format = parse_format(body)
        if output_format not in RENDER_FORMATS:
            raise V3Error(
                V3ErrorCode.INVALID_CHOICE,
                f"Unknown render format: {output_format}",
                field="format",
            )
        output = _engine.render_one(spec, output_format)
        payload = output.as_dict()
        payload["content"] = output.content
        return payload

    def manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        result = _build(spec_from_dict(body))
        return {
            "manifest": result.manifest,
            "theme": result.theme.key,
            "sections": len(result.document.all_sections),
            "pages": result.plan.total_pages,
        }

    def redact(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        spec = spec_from_dict(body)
        result = _build(spec)
        return {
            "preview": result.preview.as_dict(),
            "rules": [rule.as_dict() for rule in spec.redactions],
            "applied": list(result.preview.applied),
        }

    def validate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        spec = spec_from_dict(body)
        result = _build(spec)
        issues: list[dict[str, str]] = []
        if not result.selection.included:
            issues.append({"code": "empty_selection", "message": "No findings were selected"})
        if not result.plan.total_pages:
            issues.append({"code": "empty_layout", "message": "The design has no pages"})
        if not result.preview.is_complete:
            issues.append({"code": "redaction_leak", "message": "A redaction match persisted"})
        return {
            "valid": not issues,
            "issues": issues,
            "rules": rule_summary(spec.policy),
            "design_digest": result.design_digest,
        }

    router.add("reports", "health", health, public=True)
    router.add("reports", "themes", themes, public=True)
    router.add("reports", "formats", formats, public=True)
    router.add("reports", "design", design)
    router.add("reports", "preview", preview)
    router.add("reports", "paginate", paginate)
    router.add("reports", "render", render)
    router.add("reports", "manifest", manifest)
    router.add("reports", "redact", redact)
    router.add("reports", "validate", validate)
