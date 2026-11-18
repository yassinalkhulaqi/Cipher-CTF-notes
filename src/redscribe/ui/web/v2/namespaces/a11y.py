"""Additive v2 API namespace for accessibility, i18n, and theming workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import (
    V2Error,
    V2ErrorCode,
    compute_etag,
    require_str,
)
from redscribe.ui.web.v2.routes import RouteResult
from redscribe.v2.a11y.service import A11yService

Handler = Callable[[dict[str, Any]], RouteResult]


class Registrar(Protocol):
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


@dataclass(frozen=True, slots=True)
class RouteSpec:
    """One route exposed by the a11y namespace."""

    action: str
    description: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    mutating: bool = False


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec("health", "Report a11y namespace capabilities and feature counts."),
    RouteSpec(
        "audit",
        "Audit an element tree for accessibility problems.",
        optional=("nodes", "locale", "level", "theme", "palette"),
    ),
    RouteSpec(
        "contrast",
        "Validate a set of color pairs or a palette.",
        optional=("pairs", "palette", "level"),
    ),
    RouteSpec(
        "contrast_check",
        "Check the contrast of a single foreground and background color.",
        required=("foreground", "background"),
        optional=("level",),
    ),
    RouteSpec(
        "focus",
        "Analyze keyboard focus order for an element tree.",
        optional=("nodes", "require_skip_link", "simulate_presses"),
    ),
    RouteSpec(
        "aria",
        "Validate ARIA attributes in an element tree.",
        optional=("nodes", "strict"),
    ),
    RouteSpec(
        "aria_attribute",
        "Validate one ARIA attribute and value.",
        required=("attribute", "value"),
        optional=("role",),
    ),
    RouteSpec("roles", "Return the ARIA role registry summary."),
    RouteSpec(
        "shortcuts",
        "Validate shortcuts and optionally apply binding overrides.",
        optional=("overrides", "suggest_for", "scope"),
    ),
    RouteSpec(
        "shortcut_format",
        "Normalize and format a keyboard shortcut binding.",
        required=("binding",),
        optional=("platform",),
    ),
    RouteSpec(
        "locales",
        "List locale metadata with optional Accept-Language matching.",
        optional=("accept_language",),
    ),
    RouteSpec(
        "locale_detail",
        "Return metadata and catalog coverage for one locale.",
        required=("locale",),
    ),
    RouteSpec(
        "catalog",
        "Return a message catalog, optionally filtered by key prefixes.",
        required=("locale",),
        optional=("prefixes",),
    ),
    RouteSpec(
        "translate",
        "Translate one message key with parameters.",
        required=("locale", "key"),
        optional=("params",),
    ),
    RouteSpec("coverage", "Report translation coverage for all catalogs."),
    RouteSpec(
        "format",
        "Format a number, plural, date, datetime, or relative time value.",
        required=("kind", "value"),
        optional=("locale", "key", "min_digits", "max_digits"),
    ),
    RouteSpec(
        "rtl",
        "Return right-to-left layout helpers for text and element trees.",
        optional=("locale", "text", "nodes", "direction"),
    ),
    RouteSpec("themes", "List themes, token options, and validation status."),
    RouteSpec(
        "theme_detail", "Return one theme with contrast validation and CSS.", required=("theme",)
    ),
    RouteSpec(
        "theme_create",
        "Create a theme definition from token overrides.",
        required=("name",),
        optional=("label", "mode", "tokens", "base", "description", "accent_hue"),
    ),
    RouteSpec(
        "theme_css",
        "Return CSS custom properties for one theme.",
        required=("theme",),
        optional=("selector",),
    ),
    RouteSpec(
        "theme_compare", "Compare token values between two themes.", required=("first", "second")
    ),
    RouteSpec(
        "theme_contrast",
        "Validate contrast for themes or a custom theme payload.",
        optional=("theme", "themes", "level"),
    ),
    RouteSpec(
        "theme_fixes", "Suggest accessible token replacements for a theme.", required=("theme",)
    ),
    RouteSpec("preferences", "Return effective accessibility preferences.", optional=("profile",)),
    RouteSpec("preferences_defaults", "Return default preference values."),
    RouteSpec("preferences_schema", "Return the preference field schema."),
    RouteSpec("preferences_validate", "Validate a preference payload.", required=("preferences",)),
    RouteSpec(
        "preferences_update",
        "Merge a preference patch into a profile.",
        required=("patch",),
        optional=("profile",),
        mutating=True,
    ),
    RouteSpec(
        "preferences_replace",
        "Replace all preferences in a profile.",
        required=("preferences",),
        optional=("profile",),
        mutating=True,
    ),
    RouteSpec(
        "preferences_reset", "Reset a profile to defaults.", optional=("profile",), mutating=True
    ),
    RouteSpec("preferences_export", "Export a profile as portable data.", optional=("profile",)),
    RouteSpec(
        "preferences_import",
        "Import preference data into a profile.",
        required=("payload",),
        optional=("profile",),
        mutating=True,
    ),
    RouteSpec(
        "dashboard",
        "Build a combined accessibility and i18n dashboard.",
        optional=("locale", "nodes", "theme"),
    ),
)


def _invalid(
    message: str, *, field: str | None = None, details: dict[str, Any] | None = None
) -> V2Error:
    payload = dict(details or {})
    if field and "field" not in payload:
        payload["field"] = field
    return V2Error(400, V2ErrorCode.INVALID_REQUEST, message, details=payload)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _invalid(f"{field} must be an object", field=field)
    return {str(key): item for key, item in value.items()}


def _optional_mapping(value: Any, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, field)


def _sequence(value: Any, field: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _invalid(f"{field} must be an array", field=field)
    return list(value)


def _string_list(value: Any, field: str) -> list[str]:
    return [str(item) for item in _sequence(value, field)]


def _profile(body: Mapping[str, Any]) -> str:
    raw = body.get("profile", "default")
    text = str(raw).strip()
    if not text:
        raise _invalid("profile must not be empty", field="profile")
    if len(text) > 80:
        raise _invalid("profile is too long", field="profile")
    return text


def _result(data: Any) -> RouteResult:
    return RouteResult(data, etag=compute_etag(data))


class A11yHandlers:
    """Route handlers backed by :class:`A11yService`."""

    def __init__(self, service: A11yService) -> None:
        self._service = service

    @property
    def service(self) -> A11yService:
        return self._service

    def health(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.health())

    def audit(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.audit(body))

    def contrast(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.contrast(body))

    def contrast_check(self, body: dict[str, Any]) -> RouteResult:
        foreground = require_str(body, "foreground")
        background = require_str(body, "background")
        level = str(body.get("level") or "AA")
        try:
            return _result(self._service.check_contrast(foreground, background, level=level))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def focus(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.focus(body))

    def aria(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.aria(body))

    def aria_attribute(self, body: dict[str, Any]) -> RouteResult:
        attribute = require_str(body, "attribute")
        value = require_str(body, "value")
        role = str(body.get("role") or "")
        return _result(self._service.validate_aria_attribute(attribute, value, role=role))

    def roles(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.role_catalog())

    def shortcuts(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.shortcuts(body))

    def shortcut_format(self, body: dict[str, Any]) -> RouteResult:
        binding = body.get("binding")
        parsed: str | list[str]
        if isinstance(binding, str):
            parsed = binding
        elif isinstance(binding, Sequence) and not isinstance(binding, (str, bytes, bytearray)):
            parsed = [str(item) for item in binding]
        else:
            raise _invalid("binding must be a string or array", field="binding")
        platform = str(body.get("platform") or "desktop")
        try:
            return _result(self._service.shortcut_format(parsed, platform=platform))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def locales(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.locales(body))

    def locale_detail(self, body: dict[str, Any]) -> RouteResult:
        locale = require_str(body, "locale")
        try:
            return _result(self._service.locale_detail(locale))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def catalog(self, body: dict[str, Any]) -> RouteResult:
        locale = require_str(body, "locale")
        prefixes: tuple[str, ...] = ()
        if "prefixes" in body and body["prefixes"] is not None:
            prefixes = tuple(_string_list(body["prefixes"], "prefixes"))
        try:
            result = self._service.catalog(locale, prefixes=prefixes)
        except ValueError as exc:
            raise _invalid(str(exc)) from exc
        return _result(result)

    def translate(self, body: dict[str, Any]) -> RouteResult:
        locale = require_str(body, "locale")
        key = require_str(body, "key")
        params = _optional_mapping(body.get("params"), "params") or {}
        return _result(self._service.translate(locale, key, params))

    def coverage(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.coverage())

    def format(self, body: dict[str, Any]) -> RouteResult:
        if "kind" not in body or "value" not in body:
            raise V2Error(
                400,
                V2ErrorCode.MISSING_FIELD,
                "Both kind and value are required",
                details={"fields": ["kind", "value"]},
            )
        try:
            return _result(self._service.format(body))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def rtl(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.rtl(body))

    def themes(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.themes())

    def theme_detail(self, body: dict[str, Any]) -> RouteResult:
        name = require_str(body, "theme")
        try:
            return _result(self._service.theme_detail(name))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def theme_create(self, body: dict[str, Any]) -> RouteResult:
        try:
            return _result(self._service.theme_create(body))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def theme_css(self, body: dict[str, Any]) -> RouteResult:
        name = require_str(body, "theme")
        selector = str(body.get("selector") or ":root")
        try:
            return _result(self._service.theme_css(name, selector=selector))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def theme_compare(self, body: dict[str, Any]) -> RouteResult:
        first = require_str(body, "first")
        second = require_str(body, "second")
        try:
            return _result(self._service.theme_compare(first, second))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def theme_contrast(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.theme_contrast(body))

    def theme_fixes(self, body: dict[str, Any]) -> RouteResult:
        name = require_str(body, "theme")
        try:
            return _result(self._service.theme_fixes(name))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def preferences(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.preferences(_profile(body)))

    def preferences_defaults(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.preferences_defaults())

    def preferences_schema(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.preferences_schema())

    def preferences_validate(self, body: dict[str, Any]) -> RouteResult:
        payload = _mapping(body.get("preferences"), "preferences")
        return _result(self._service.preferences_validate(payload))

    def preferences_update(self, body: dict[str, Any]) -> RouteResult:
        patch = _mapping(body.get("patch"), "patch")
        try:
            return _result(self._service.preferences_update(patch, profile=_profile(body)))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def preferences_replace(self, body: dict[str, Any]) -> RouteResult:
        payload = _mapping(body.get("preferences"), "preferences")
        try:
            return _result(self._service.preferences_replace(payload, profile=_profile(body)))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def preferences_reset(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.preferences_reset(profile=_profile(body)))

    def preferences_export(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.preferences_export(profile=_profile(body)))

    def preferences_import(self, body: dict[str, Any]) -> RouteResult:
        payload = _mapping(body.get("payload"), "payload")
        try:
            return _result(self._service.preferences_import(payload, profile=_profile(body)))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc

    def dashboard(self, body: dict[str, Any]) -> RouteResult:
        return _result(self._service.dashboard(body))


class A11yNamespace:
    """Registration wrapper for the a11y namespace."""

    def __init__(self, service: A11yService) -> None:
        self._service = service
        self.handlers = A11yHandlers(service)

    @property
    def service(self) -> A11yService:
        return self._service

    def routes(self) -> tuple[str, ...]:
        return tuple(f"a11y.{spec.action}" for spec in ROUTE_SPECS)

    def handler_map(self) -> dict[str, Handler]:
        return {spec.action: getattr(self.handlers, spec.action) for spec in ROUTE_SPECS}

    def register(self, api: Registrar) -> tuple[str, ...]:
        register = getattr(api, "register", None)
        if register is None:
            register = getattr(api, "_register", None)
        if not callable(register):
            raise TypeError("API does not expose a route registration method")
        for spec in ROUTE_SPECS:
            register(
                f"a11y.{spec.action}",
                getattr(self.handlers, spec.action),
                spec.description,
                required=spec.required,
                optional=spec.optional,
                mutating=spec.mutating,
                entity_type="a11y",
            )
        return self.routes()


def register(api: Registrar) -> A11yNamespace:
    """Register the a11y namespace on an API v2 registrar."""
    namespace = A11yNamespace(A11yService())
    namespace.register(api)
    return namespace


def register_with_service(service: A11yService) -> A11yNamespace:
    """Build a namespace around a custom service instance."""
    return A11yNamespace(service)


def route_names() -> tuple[str, ...]:
    """Return all route names exposed by this namespace."""
    return tuple(f"a11y.{spec.action}" for spec in ROUTE_SPECS)


def route_specs() -> tuple[dict[str, Any], ...]:
    """Return route metadata for introspection and tests."""
    return tuple(
        {
            "action": spec.action,
            "description": spec.description,
            "required": list(spec.required),
            "optional": list(spec.optional),
            "mutating": spec.mutating,
        }
        for spec in ROUTE_SPECS
    )
