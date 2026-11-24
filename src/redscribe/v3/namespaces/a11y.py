"""A11y refinement namespace routes for the V3 API.

Registered through dynamic namespace discovery; this module never edits a
shared B00 registry. Every route is added with
``router.add("a11y", action, handler)``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from redscribe.v3.a11y_refinement.models import MotionMode, SyncStrategy
from redscribe.v3.a11y_refinement.service import DEFAULT_SURFACES, A11yRefinementService
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router

MAX_AUDIT_LEVEL = "AAA"
SERVICE = A11yRefinementService()


def _call(action: str, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run a service call and translate validation errors into V3 errors."""
    try:
        return callback()
    except (ValueError, KeyError, TypeError) as error:
        raise V3Error(
            V3ErrorCode.INVALID_REQUEST,
            f"a11y/{action}: {error}",
        ) from error


def _string(body: Mapping[str, Any], key: str, default: str) -> str:
    """Read a string field with a default."""
    value = body.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a string", field=key)
    return value or default


def _mapping(body: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Read an optional nested object."""
    value = body.get(key)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be an object", field=key)
    return value


def _sequence(body: Mapping[str, Any], key: str) -> Sequence[Any]:
    """Read an optional list field."""
    value = body.get(key, ())
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a list", field=key)
    return value


def _choice(value: str, options: Sequence[str], field: str) -> str:
    """Validate a value against a set of choices."""
    normalized = value.strip().lower()
    if normalized not in options:
        raise V3Error(
            V3ErrorCode.INVALID_CHOICE,
            f"Invalid {field}: {value}",
            field=field,
        )
    return normalized


def register(router: V3Router) -> None:
    """Register all a11y refinement routes on the supplied router."""

    def health(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return SERVICE.health()

    def rules(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        level = _choice(_string(body, "level", MAX_AUDIT_LEVEL), ("a", "aa", "aaa"), "level")
        return SERVICE.wcag_rules(level=level.upper())

    def surfaces(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "surfaces": [spec.as_dict() for spec in DEFAULT_SURFACES],
            "names": list(SERVICE.surface_names()),
        }

    def audit(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        name = _string(body, "surface", "")
        level = _string(body, "level", "")
        return _call("audit", lambda: SERVICE.audit(name, level=level or None))

    def audit_all(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        level = _string(body, "level", "AA")
        return _call("audit_all", lambda: SERVICE.audit_all(level=level))

    def contrast(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _call("contrast", lambda: SERVICE.contrast(body))

    def theme_contrast(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _call("theme_contrast", lambda: SERVICE.dual_theme(body))

    def format_one(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _call("format", lambda: SERVICE.format_one(body))

    def format_many(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        _sequence(body, "requests")
        return _call("format_batch", lambda: SERVICE.format_many(body))

    def round_trip(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        value = body.get("value", 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'value' must be numeric", field="value")
        locale = _string(body, "locale", "en")
        digits = int(body.get("digits", 2))
        return _call("round_trip", lambda: SERVICE.round_trip(value, locale, digits))

    def translate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        locale = _string(body, "locale", "en")
        key = _string(body, "key", "")
        params = _mapping(body, "params")
        return _call("translate", lambda: SERVICE.translation(locale, key, params))

    def locales(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        header = _string(body, "accept_language", "")
        return SERVICE.locales(accept_language=header)

    def rtl(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        pane = _string(body, "pane", "command-center")
        locale = _string(body, "locale", "en")
        text = _string(body, "text", "")
        override = _string(body, "override", "")
        return _call("rtl", lambda: SERVICE.rtl(pane, locale, text=text, override=override))

    def rtl_manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        locale = _string(body, "locale", "en")
        override = _string(body, "override", "")
        return SERVICE.rtl_manifest(locale, override=override)

    def bidi(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        text = _string(body, "text", "")
        locale = _string(body, "locale", "en")
        override = _string(body, "override", "")
        return SERVICE.bidi(text, locale, override=override)

    def keyboard(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        locale = _string(body, "locale", "en")
        platform = _choice(
            _string(body, "platform", "desktop"), ("desktop", "mac", "web"), "platform"
        )
        overrides = _mapping(body, "overrides")
        return _call(
            "keyboard",
            lambda: SERVICE.keyboard(locale=locale, platform=platform, overrides=overrides),
        )

    def keyboard_help(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        locale = _string(body, "locale", "en")
        platform = _choice(
            _string(body, "platform", "desktop"), ("desktop", "mac", "web"), "platform"
        )
        return _call(
            "keyboard_help", lambda: SERVICE.keyboard_help(locale=locale, platform=platform)
        )

    def keyboard_lookup(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        pressed = _sequence(body, "pressed")
        strings = [str(item) for item in pressed]
        scope = _string(body, "scope", "global")
        locale = _string(body, "locale", "en")
        platform = _string(body, "platform", "desktop")
        return _call(
            "keyboard_lookup",
            lambda: SERVICE.keyboard_lookup(strings, scope=scope, locale=locale, platform=platform),
        )

    def keyboard_group(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        group = _string(body, "group", "navigation")
        locale = _string(body, "locale", "en")
        platform = _string(body, "platform", "desktop")
        return SERVICE.keyboard_group(group, locale=locale, platform=platform)

    def preferences(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        profile = _string(body, "profile", "default")
        return SERVICE.preferences(profile=profile)

    def preferences_update(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        profile = _string(body, "profile", "default")
        patch = _mapping(body, "patch") or body
        return _call(
            "preferences_update",
            lambda: SERVICE.preferences_update(patch, profile=profile),
        )

    def preferences_sync(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        profile = _string(body, "profile", "default")
        raw_strategy = _string(body, "strategy", "merge")
        strategy_name = _choice(
            raw_strategy,
            tuple(item.value for item in SyncStrategy),
            "strategy",
        )
        return _call(
            "preferences_sync",
            lambda: SERVICE.preferences_sync(
                _mapping(body, "remote") or body,
                profile=profile,
                strategy=SyncStrategy(strategy_name),
            ),
        )

    def motion(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        mode = _choice(
            _string(body, "mode", "full"),
            tuple(item.value for item in MotionMode),
            "mode",
        )
        return SERVICE.motion(mode)

    def dashboard(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _call("dashboard", lambda: SERVICE.dashboard(body))

    def export(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return SERVICE.export()

    router.add("a11y", "health", health, public=True)
    router.add("a11y", "rules", rules, public=True)
    router.add("a11y", "surfaces", surfaces, public=True)
    router.add("a11y", "audit", audit)
    router.add("a11y", "audit_all", audit_all)
    router.add("a11y", "contrast", contrast)
    router.add("a11y", "theme_contrast", theme_contrast)
    router.add("a11y", "format", format_one)
    router.add("a11y", "format_batch", format_many)
    router.add("a11y", "round_trip", round_trip)
    router.add("a11y", "translate", translate)
    router.add("a11y", "locales", locales, public=True)
    router.add("a11y", "rtl", rtl)
    router.add("a11y", "rtl_manifest", rtl_manifest)
    router.add("a11y", "bidi", bidi)
    router.add("a11y", "keyboard", keyboard)
    router.add("a11y", "keyboard_help", keyboard_help)
    router.add("a11y", "keyboard_lookup", keyboard_lookup)
    router.add("a11y", "keyboard_group", keyboard_group)
    router.add("a11y", "preferences", preferences)
    router.add("a11y", "preferences_update", preferences_update)
    router.add("a11y", "preferences_sync", preferences_sync)
    router.add("a11y", "motion", motion, public=True)
    router.add("a11y", "dashboard", dashboard)
    router.add("a11y", "export", export)


__all__ = ["SERVICE", "register"]
