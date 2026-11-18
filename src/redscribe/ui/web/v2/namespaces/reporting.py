"""Reporting studio API v2 namespace.

The module is additive: ``register(api)`` attaches reporting routes to an
existing ``ApiV2`` registry without editing the shared route table. Handlers
are plain functions so they can also be invoked directly from tests and other
in-process callers.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import (
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_str,
    require_str,
)
from redscribe.ui.web.v2.routes import RouteResult
from redscribe.v2.reporting.models import REPORT_FORMATS, RedactionRule
from redscribe.v2.reporting.pipeline import ReportingService, format_options
from redscribe.v2.reporting.print_layout import profile_summary
from redscribe.v2.reporting.redaction import (
    builtin_redactions,
    preview_redaction,
    redact_text,
    sorted_rules,
)
from redscribe.v2.reporting.sections import (
    move_section,
    reorder_sections,
    section_stats,
    section_titles,
)
from redscribe.v2.reporting.serialization import parse_section
from redscribe.v2.reporting.templates import get_template, template_summaries
from redscribe.v2.reporting.validation import validate_format

Handler = Callable[[dict[str, Any]], RouteResult]


class Registrar(Protocol):
    """The minimal route-registration surface required by this namespace."""

    @property
    def vault(self) -> Vault: ...

    def register(
        self,
        name: str,
        handler: Handler,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None: ...


ROUTE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "action": "health",
        "description": "Report reporting-studio availability, formats, and templates.",
        "required": (),
        "optional": (),
    },
    {
        "action": "templates",
        "description": "List report templates available to the builder.",
        "required": (),
        "optional": (),
    },
    {
        "action": "template",
        "description": "Return one full report template definition.",
        "required": ("key",),
        "optional": (),
    },
    {
        "action": "profiles",
        "description": "List available print profiles and page dimensions.",
        "required": (),
        "optional": (),
    },
    {
        "action": "config_schema",
        "description": "Describe report configuration fields for editor tooling.",
        "required": (),
        "optional": (),
    },
    {
        "action": "sections",
        "description": "Return a template outline or parse a supplied section tree.",
        "required": (),
        "optional": ("key", "sections"),
    },
    {
        "action": "source",
        "description": "Create a deterministic vault source snapshot.",
        "required": (),
        "optional": ("tag", "status", "root_id", "generated_at"),
    },
    {
        "action": "build",
        "description": "Build a deterministic report document from config.",
        "required": (),
        "optional": ("title", "template", "generated_at", "findings", "sections"),
    },
    {
        "action": "preview",
        "description": "Return a lightweight report preview for the builder.",
        "required": (),
        "optional": ("title", "template", "generated_at"),
    },
    {
        "action": "validate",
        "description": "Validate a report configuration without building it.",
        "required": (),
        "optional": ("title", "template", "generated_at"),
    },
    {
        "action": "severity",
        "description": "Return severity analytics for a report configuration.",
        "required": (),
        "optional": ("title", "template", "generated_at"),
    },
    {
        "action": "inclusion",
        "description": "Explain which source notes matched inclusion rules.",
        "required": (),
        "optional": ("title", "template", "generated_at"),
    },
    {
        "action": "render",
        "description": "Render a report into Markdown, HTML, JSON, or print HTML.",
        "required": ("format",),
        "optional": ("profile", "generated_at", "title", "template"),
    },
    {
        "action": "export",
        "description": "Export a report and optionally write it under a directory.",
        "required": ("format",),
        "optional": ("profile", "generated_at", "directory", "title", "template"),
    },
    {
        "action": "bundle",
        "description": "Export a report bundle with several formats and a manifest.",
        "required": ("directory",),
        "optional": ("formats", "generated_at", "profile", "title", "template"),
    },
    {
        "action": "manifest",
        "description": "Return the reproducibility manifest for a configuration.",
        "required": (),
        "optional": ("generated_at", "title", "template"),
    },
    {
        "action": "redact",
        "description": "Apply and preview redaction rules against sample text.",
        "required": ("text",),
        "optional": ("redactions", "use_defaults", "context"),
    },
    {
        "action": "redaction_rules",
        "description": "Return the built-in redaction rule set.",
        "required": (),
        "optional": ("include_hosts",),
    },
    {
        "action": "reorder",
        "description": "Apply a section ordering change to a supplied outline.",
        "required": ("sections", "parent_id", "order"),
        "optional": (),
    },
    {
        "action": "move",
        "description": "Move one section inside a supplied outline.",
        "required": ("sections", "identifier", "parent_id", "index"),
        "optional": (),
    },
)

CONFIG_FIELDS: tuple[dict[str, object], ...] = (
    {"name": "title", "type": "string", "required": True, "description": "Report title."},
    {"name": "template", "type": "string", "required": False, "description": "Template key."},
    {"name": "client", "type": "string", "required": False, "description": "Client name."},
    {"name": "author", "type": "string", "required": False, "description": "Report author."},
    {
        "name": "classification",
        "type": "string",
        "required": False,
        "description": "public, internal, confidential, or restricted.",
    },
    {"name": "scope", "type": "array", "required": False, "description": "Scope statements."},
    {"name": "findings", "type": "array", "required": False, "description": "Finding objects."},
    {"name": "sections", "type": "array", "required": False, "description": "Section tree."},
    {"name": "rules", "type": "array", "required": False, "description": "Inclusion rules."},
    {"name": "redactions", "type": "array", "required": False, "description": "Redaction rules."},
    {"name": "tags", "type": "array", "required": False, "description": "Source tag filter."},
    {
        "name": "statuses",
        "type": "array",
        "required": False,
        "description": "Source status filter.",
    },
    {
        "name": "minimum_severity",
        "type": "string",
        "required": False,
        "description": "Lowest severity to include.",
    },
    {"name": "page_size", "type": "string", "required": False, "description": "Paper size."},
    {
        "name": "orientation",
        "type": "string",
        "required": False,
        "description": "Page orientation.",
    },
    {
        "name": "print_profile",
        "type": "string",
        "required": False,
        "description": "Print layout profile key.",
    },
    {
        "name": "include_evidence",
        "type": "boolean",
        "required": False,
        "description": "Include evidence sections.",
    },
    {
        "name": "include_appendices",
        "type": "boolean",
        "required": False,
        "description": "Include report appendices.",
    },
    {"name": "notes", "type": "string", "required": False, "description": "Closing notes."},
    {
        "name": "format",
        "type": "string",
        "required": True,
        "description": "markdown, html, json, or print.",
    },
)


def _config(body: dict[str, Any], service: ReportingService) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in body.items()
        if key not in ("format", "profile", "directory", "generated_at", "text")
    }
    return payload


def _generated_at(body: dict[str, Any]) -> str:
    return optional_str(body, "generated_at", default="") or ""


def _invalid(message: str, *, details: dict[str, Any] | None = None) -> V2Error:
    return V2Error(400, V2ErrorCode.INVALID_REQUEST, message, details=details)


class ReportingHandlers:
    """Stateless handlers bound to one reporting service."""

    def __init__(self, service: ReportingService) -> None:
        self._service = service

    @property
    def service(self) -> ReportingService:
        return self._service

    def health(self, body: dict[str, Any]) -> RouteResult:
        data = {
            "ok": True,
            "namespace": "reporting",
            "formats": list(REPORT_FORMATS),
            "templates": [item["key"] for item in template_summaries()],
            "profiles": list(profile_summary()),
        }
        return RouteResult(data, etag=compute_etag(data))

    def templates(self, body: dict[str, Any]) -> RouteResult:
        data = {"templates": list(template_summaries())}
        return RouteResult(data, etag=compute_etag(data))

    def template(self, body: dict[str, Any]) -> RouteResult:
        key = require_str(body, "key")
        try:
            data = get_template(key).as_dict()
        except ValueError as exc:
            raise _invalid(str(exc), details={"field": "key"}) from exc
        return RouteResult(data, etag=compute_etag(data))

    def profiles(self, body: dict[str, Any]) -> RouteResult:
        data = {"profiles": list(profile_summary())}
        return RouteResult(data, etag=compute_etag(data))

    def config_schema(self, body: dict[str, Any]) -> RouteResult:
        data = {
            "version": "1.0.0",
            "fields": [dict(field) for field in CONFIG_FIELDS],
            "formats": format_options(),
        }
        return RouteResult(data, etag=compute_etag(data))

    def sections(self, body: dict[str, Any]) -> RouteResult:
        raw_sections = body.get("sections")
        if raw_sections is None:
            key = optional_str(body, "key", default="engagement") or "engagement"
            try:
                sections = get_template(key).sections
            except ValueError as exc:
                raise _invalid(str(exc), details={"field": "key"}) from exc
        else:
            if not isinstance(raw_sections, Sequence) or isinstance(raw_sections, str):
                raise _invalid("sections must be an array", details={"field": "sections"})
            sections = tuple(parse_section(item) for item in raw_sections)
        data = {
            "sections": [section.as_dict() for section in sections],
            "stats": section_stats(sections),
            "outline": list(section_titles(sections)),
        }
        return RouteResult(data, etag=compute_etag(data))

    def source(self, body: dict[str, Any]) -> RouteResult:
        try:
            data = self._service.source(
                _generated_at(body),
                **{key: body[key] for key in ("tag", "status", "root_id") if key in body},
            )
        except ValueError as exc:
            raise _invalid(str(exc)) from exc
        return RouteResult(data, etag=compute_etag(data))

    def build(self, body: dict[str, Any]) -> RouteResult:
        document = self._service.build(
            _config(body, self._service), generated_at=_generated_at(body)
        )
        data = document.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def preview(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.preview(_config(body, self._service), generated_at=_generated_at(body))
        return RouteResult(data, etag=compute_etag(data))

    def validate(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.validate(
            _config(body, self._service), generated_at=_generated_at(body)
        )
        return RouteResult(data, etag=compute_etag(data))

    def severity(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.severity(
            _config(body, self._service), generated_at=_generated_at(body)
        )
        return RouteResult(data, etag=compute_etag(data))

    def inclusion(self, body: dict[str, Any]) -> RouteResult:
        data = self._service.inclusion_report(
            _config(body, self._service), generated_at=_generated_at(body)
        )
        return RouteResult(data, etag=compute_etag(data))

    def render(self, body: dict[str, Any]) -> RouteResult:
        fmt = self._format(body)
        rendered = self._service.render(
            _config(body, self._service),
            fmt,
            generated_at=_generated_at(body),
            profile=optional_str(body, "profile", default="") or "",
        )
        data = rendered.as_dict()
        return RouteResult(data, etag=compute_etag(data))

    def export(self, body: dict[str, Any]) -> RouteResult:
        fmt = self._format(body)
        try:
            data = self._service.export(
                _config(body, self._service),
                fmt,
                generated_at=_generated_at(body),
                profile=optional_str(body, "profile", default="") or "",
                directory=optional_str(body, "directory", default="") or None,
            )
        except OSError as exc:
            raise V2Error(500, V2ErrorCode.INTERNAL, "Could not write report export") from exc
        return RouteResult(data, etag=compute_etag(data))

    def bundle(self, body: dict[str, Any]) -> RouteResult:
        directory = require_str(body, "directory")
        raw_formats = body.get("formats", ("markdown", "html", "json"))
        if not isinstance(raw_formats, Sequence) or isinstance(raw_formats, str):
            raise _invalid("formats must be an array", details={"field": "formats"})
        formats = tuple(str(item) for item in raw_formats)
        try:
            data = self._service.bundle(
                _config(body, self._service),
                generated_at=_generated_at(body),
                directory=directory,
                formats=formats,
            )
        except (OSError, ValueError) as exc:
            raise _invalid(str(exc)) from exc
        return RouteResult(data, etag=compute_etag(data))

    def manifest(self, body: dict[str, Any]) -> RouteResult:
        document = self._service.build(
            _config(body, self._service), generated_at=_generated_at(body)
        )
        data = self._service.manifest(document, None)
        return RouteResult(data, etag=compute_etag(data))

    def redact(self, body: dict[str, Any]) -> RouteResult:
        text = require_str(body, "text")
        rules = _redaction_rules(body)
        result = redact_text(text, rules)
        context_raw = body.get("context", 24)
        if isinstance(context_raw, bool) or not isinstance(context_raw, int):
            raise _invalid("context must be an integer", details={"field": "context"})
        data = {
            **result.as_dict(),
            "preview": preview_redaction(text, rules, context=context_raw),
            "rules": [rule.as_dict() for rule in sorted_rules(rules)],
        }
        return RouteResult(data, etag=compute_etag(data))

    def redaction_rules(self, body: dict[str, Any]) -> RouteResult:
        include_hosts = body.get("include_hosts", False)
        if not isinstance(include_hosts, bool):
            raise _invalid("include_hosts must be a boolean", details={"field": "include_hosts"})
        rules = builtin_redactions(include_hosts=include_hosts)
        data = {"rules": [rule.as_dict() for rule in rules]}
        return RouteResult(data, etag=compute_etag(data))

    def reorder(self, body: dict[str, Any]) -> RouteResult:
        sections = _sections_argument(body)
        parent_id = require_str(body, "parent_id")
        order = _string_list(body.get("order"), "order")
        reordered = reorder_sections(sections, parent_id, order)
        data = {"sections": [section.as_dict() for section in reordered]}
        return RouteResult(data, etag=compute_etag(data))

    def move(self, body: dict[str, Any]) -> RouteResult:
        sections = _sections_argument(body)
        identifier = require_str(body, "identifier")
        parent_id = require_str(body, "parent_id")
        index = body.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise _invalid("index must be an integer", details={"field": "index"})
        try:
            moved = move_section(sections, identifier, parent_id=parent_id, index=index)
        except ValueError as exc:
            raise _invalid(str(exc)) from exc
        data = {"sections": [section.as_dict() for section in moved]}
        return RouteResult(data, etag=compute_etag(data))

    def _format(self, body: dict[str, Any]) -> str:
        raw = require_str(body, "format")
        try:
            return validate_format(raw)
        except ValueError as exc:
            raise V2Error(
                400,
                V2ErrorCode.INVALID_CHOICE,
                str(exc),
                details={"field": "format"},
            ) from exc


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise _invalid(f"{field} must be an array", details={"field": field})
    return tuple(str(item) for item in value)


def _sections_argument(body: dict[str, Any]) -> tuple[Any, ...]:
    raw = body.get("sections")
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise _invalid("sections must be an array", details={"field": "sections"})
    return tuple(parse_section(item) for item in raw)


def _redaction_rules(body: dict[str, Any]) -> tuple[RedactionRule, ...]:
    raw = body.get("redactions")
    defaults = body.get("use_defaults", True)
    if not isinstance(defaults, bool):
        raise _invalid("use_defaults must be a boolean", details={"field": "use_defaults"})
    rules: list[RedactionRule] = []
    if raw is not None:
        if not isinstance(raw, Sequence) or isinstance(raw, str):
            raise _invalid("redactions must be an array", details={"field": "redactions"})
        from redscribe.v2.reporting.serialization import parse_redaction

        rules.extend(parse_redaction(item) for item in raw)
    if defaults or not rules:
        rules.extend(builtin_redactions())
    return tuple(rules)


class ReportingNamespace:
    """A registered reporting namespace and its handlers."""

    def __init__(self, service: ReportingService) -> None:
        self._service = service
        self.handlers = ReportingHandlers(service)

    @property
    def service(self) -> ReportingService:
        return self._service

    def routes(self) -> tuple[str, ...]:
        return tuple(f"reporting.{spec['action']}" for spec in ROUTE_SPECS)

    def register(self, api: Registrar) -> tuple[str, ...]:
        """Attach all reporting routes to an API v2 registry."""
        register = getattr(api, "register", None)
        if register is None:
            register = getattr(api, "_register", None)
        if not callable(register):
            raise TypeError("API does not expose a route registration method")
        by_action = dict(self.handler_map())
        for spec in ROUTE_SPECS:
            action = str(spec["action"])
            handler = by_action[action]
            register(
                f"reporting.{action}",
                handler,
                str(spec["description"]),
                required=tuple(spec["required"]),
                optional=tuple(spec["optional"]),
                mutating=False,
                entity_type="report",
            )
        return self.routes()

    def handler_map(self) -> dict[str, Handler]:
        return {
            "health": self.handlers.health,
            "templates": self.handlers.templates,
            "template": self.handlers.template,
            "profiles": self.handlers.profiles,
            "config_schema": self.handlers.config_schema,
            "sections": self.handlers.sections,
            "source": self.handlers.source,
            "build": self.handlers.build,
            "preview": self.handlers.preview,
            "validate": self.handlers.validate,
            "severity": self.handlers.severity,
            "inclusion": self.handlers.inclusion,
            "render": self.handlers.render,
            "export": self.handlers.export,
            "bundle": self.handlers.bundle,
            "manifest": self.handlers.manifest,
            "redact": self.handlers.redact,
            "redaction_rules": self.handlers.redaction_rules,
            "reorder": self.handlers.reorder,
            "move": self.handlers.move,
        }


def register(api: Registrar) -> ReportingNamespace:
    """Register the reporting namespace on an existing API v2 instance."""
    vault = api.vault
    namespace = ReportingNamespace(ReportingService(vault))
    namespace.register(api)
    return namespace


def register_with_vault(vault: Vault) -> ReportingNamespace:
    """Create a namespace without attaching it to an API registry."""
    return ReportingNamespace(ReportingService(vault))


def route_names() -> tuple[str, ...]:
    """Return all reporting route names."""
    return tuple(f"reporting.{spec['action']}" for spec in ROUTE_SPECS)


def route_specs() -> tuple[dict[str, Any], ...]:
    """Return route metadata for schema documentation."""
    return tuple(dict(spec) for spec in ROUTE_SPECS)
