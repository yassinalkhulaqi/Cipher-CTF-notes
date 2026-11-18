"""Application service coordinating accessibility, i18n, and theme workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from redscribe.v2.a11y.aria import role_summary, validate_attribute, validate_tree
from redscribe.v2.a11y.audit import (
    AccessibilityAuditor,
    audit_payload,
    audit_summary,
    nodes_from_payload,
)
from redscribe.v2.a11y.contrast import (
    build_report,
    check_pair,
    grade_contrast,
    palette_pairs,
    suggest_foreground,
)
from redscribe.v2.a11y.focus import analyze_focus_order, focus_summary, simulate_tabs
from redscribe.v2.a11y.i18n.catalogs import CatalogManager, MessageCatalog
from redscribe.v2.a11y.i18n.formatting import (
    format_date,
    format_datetime,
    format_number,
    format_relative_time,
    pluralize,
)
from redscribe.v2.a11y.i18n.locales import (
    all_locales,
    best_match_header,
    fallback_chain,
    locale_options,
    locale_summary,
)
from redscribe.v2.a11y.i18n.rtl import (
    analyze_rtl_tree,
    bidi_warnings,
    direction_css_vars,
    isolate_text,
    mirror_text,
)
from redscribe.v2.a11y.models import FocusMode, ThemeDefinition, WcagLevel
from redscribe.v2.a11y.preferences import (
    MemoryPreferenceStore,
    PreferenceIssue,
    PreferenceService,
    default_preferences,
    export_preferences,
    import_preferences,
    preference_defaults_payload,
    preference_schema,
    validate_preferences,
)
from redscribe.v2.a11y.shortcuts import (
    ShortcutRegistry,
    default_shortcuts,
    format_binding,
    normalize_binding,
    parse_binding,
    shortcut_groups,
    suggest_binding,
)
from redscribe.v2.a11y.theme_contrast import (
    apply_theme_fixes,
    contrast_grid,
    suggest_theme_fixes,
    theme_contrast_score,
    theme_issue_summary,
    validate_theme,
    validate_themes,
)
from redscribe.v2.a11y.themes import (
    BUILTIN_THEMES,
    ThemeRegistry,
    create_theme,
    theme_css,
    theme_diff,
    theme_from_payload,
    theme_summary,
    themes_css,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class A11yService:
    """Facade used by the v2 API namespace."""

    _preferences: PreferenceService = field(
        default_factory=lambda: PreferenceService(MemoryPreferenceStore())
    )
    _catalogs: CatalogManager = field(default_factory=CatalogManager)
    _themes: ThemeRegistry = field(default_factory=ThemeRegistry)
    _shortcuts: ShortcutRegistry = field(default_factory=default_shortcuts)

    @property
    def preference_service(self) -> PreferenceService:
        return self._preferences

    @property
    def catalog_manager(self) -> CatalogManager:
        return self._catalogs

    @property
    def theme_registry(self) -> ThemeRegistry:
        return self._themes

    @property
    def shortcut_registry(self) -> ShortcutRegistry:
        return self._shortcuts

    def health(self) -> dict[str, Any]:
        """Report namespace capabilities and default settings."""
        return {
            "ok": True,
            "namespace": "a11y",
            "features": [
                "accessibility_audit",
                "contrast_checking",
                "focus_order",
                "aria_validation",
                "shortcut_registry",
                "message_catalogs",
                "pluralization",
                "date_number_formatting",
                "rtl_helpers",
                "theme_tokens",
                "theme_contrast",
                "preference_persistence",
            ],
            "locales": len(all_locales()),
            "catalogs": len(self._catalogs.locales),
            "themes": len(self._themes.names),
            "shortcuts": len(self._shortcuts),
            "wcag_levels": [level.value for level in WcagLevel],
        }

    def audit(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Run a full accessibility audit."""
        level = str(payload.get("level") or "AA")
        if level not in {item.value for item in WcagLevel}:
            raise ValueError(f"Unknown WCAG level: {level}")
        report = audit_payload(payload, locale=str(payload.get("locale") or "en"), level=level)
        result = report.as_dict()
        result["summary"] = audit_summary(report)
        return result

    def contrast(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate contrast pairs."""
        pairs = payload.get("pairs")
        palette = None
        if pairs is None:
            palette = payload.get("palette") or {}
            pairs = palette_pairs(palette, level=str(payload.get("level") or "AA"))
        if (
            isinstance(pairs, Sequence)
            and not isinstance(pairs, (str, bytes, bytearray))
            and all(isinstance(item, Mapping) for item in pairs)
        ):
            normalized: dict[str, Any] = {}
            for index, item in enumerate(pairs):
                entry = {str(key): value for key, value in item.items()}
                name = str(entry.pop("name", f"pair_{index + 1}"))
                normalized[name] = entry
            pairs = normalized
        report = build_report(pairs, level=str(payload.get("level") or "AA"))
        result = report.as_dict()
        result["grades"] = [
            grade_contrast(
                pair.ratio,
                font_size=pair.font_size,
                bold=pair.bold,
            )
            for pair in report.pairs
        ]
        return result

    def check_contrast(
        self,
        foreground: str,
        background: str,
        *,
        level: str = "AA",
    ) -> dict[str, Any]:
        """Check one color pair and return its grade."""
        pair = check_pair("custom", foreground, background, level=level)
        return {
            **pair.as_dict(),
            "grade": grade_contrast(pair.ratio, font_size=pair.font_size, bold=pair.bold),
            "suggestion": suggest_foreground(background, minimum=pair.required).to_hex(),
        }

    def focus(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Analyze focus order for an element tree."""
        nodes = nodes_from_payload(payload.get("nodes") or [])
        report = analyze_focus_order(
            nodes,
            require_skip_link=bool(payload.get("require_skip_link", True)),
        )
        result = report.as_dict()
        result["summary"] = focus_summary(report)
        presses = payload.get("simulate_presses")
        if isinstance(presses, int) and not isinstance(presses, bool) and presses > 0:
            result["simulation"] = [
                step.as_dict() for step in simulate_tabs(nodes, presses=presses)
            ]
        return result

    def aria(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate ARIA attributes in an element tree."""
        nodes = nodes_from_payload(payload.get("nodes") or [])
        return validate_tree(nodes, strict=bool(payload.get("strict", True))).as_dict()

    def validate_aria_attribute(
        self,
        attribute: str,
        value: str,
        *,
        role: str = "",
    ) -> dict[str, Any]:
        """Validate one ARIA attribute value."""
        problems = validate_attribute(attribute, value, role=role)
        return {
            "attribute": attribute,
            "value": value,
            "role": role,
            "valid": not problems,
            "problems": problems,
        }

    def role_catalog(self) -> dict[str, Any]:
        """Return ARIA role registry metadata."""
        return role_summary()

    def shortcuts(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate shortcuts or apply requested overrides."""
        registry = self._shortcuts
        overrides = payload.get("overrides")
        if isinstance(overrides, Mapping):
            registry = ShortcutRegistry(registry.values())
            for action, keys in overrides.items():
                if (
                    isinstance(keys, Sequence)
                    and not isinstance(keys, str)
                    and str(action) in registry
                ):
                    registry.update_keys(str(action), keys)
        report = registry.validate()
        result = report.as_dict()
        result["groups"] = shortcut_groups(registry)
        suggestion_for = payload.get("suggest_for")
        if isinstance(suggestion_for, str) and suggestion_for:
            try:
                result["suggestion"] = suggest_binding(
                    registry, suggestion_for, scope=self._scope(payload)
                )
            except ValueError as exc:
                result["suggestion_error"] = str(exc)
        return result

    def _scope(self, payload: Mapping[str, Any]) -> FocusMode:
        raw = str(payload.get("scope") or "global")
        try:
            return FocusMode(raw)
        except ValueError:
            return FocusMode.GLOBAL

    def shortcut_format(
        self,
        binding: str | Sequence[str],
        *,
        platform: str = "desktop",
    ) -> dict[str, Any]:
        """Format a shortcut binding for display."""
        parsed = parse_binding(binding)
        return {
            "keys": list(parsed.keys),
            "display": format_binding(parsed.keys, platform=platform),
            "binding": parsed.binding,
            "normalized": list(normalize_binding(binding)),
        }

    def locales(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return locale metadata and matching options."""
        requested = payload.get("accept_language")
        matched = None
        if isinstance(requested, str) and requested:
            matched = best_match_header(requested, [info.code for info in all_locales()])
        return {
            "locales": [info.as_dict() for info in all_locales()],
            "options": locale_options(),
            "matched": matched,
            "details": {info.code: locale_summary(info.code) for info in all_locales()},
        }

    def locale_detail(self, locale: str) -> dict[str, Any]:
        """Return one locale summary."""
        summary = locale_summary(locale)
        if not summary.get("supported"):
            raise ValueError(f"Unknown locale: {locale}")
        return {
            **summary,
            "fallbacks": list(fallback_chain(locale)),
            "messages": self._catalogs.coverage(locale),
        }

    def catalog(self, locale: str, *, prefixes: Sequence[str] = ()) -> dict[str, Any]:
        """Return a message catalog."""
        messages = self._catalogs.catalog(locale)
        if messages is None:
            raise ValueError(f"Unknown catalog: {locale}")
        selected = messages.subset(prefixes) if prefixes else messages
        return selected.as_dict()

    def translate(
        self,
        locale: str,
        key: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Translate one message key."""
        translated = self._catalogs.translate(locale, key, **dict(params or {}))
        return {
            "locale": locale,
            "key": key,
            "message": translated,
            "missing": translated == key,
        }

    def coverage(self) -> dict[str, Any]:
        """Return translation coverage for all catalogs."""
        return self._catalogs.coverage_report()

    def format(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Format values using locale-aware helpers."""
        locale = str(payload.get("locale") or "en")
        kind = str(payload.get("kind") or "number")
        value = payload.get("value")
        if kind == "number":
            number = (
                value if isinstance(value, (int, float, str)) and not isinstance(value, bool) else 0
            )
            return {
                "kind": kind,
                "value": format_number(
                    number,
                    locale=locale,
                    minimum_fraction_digits=int(payload.get("min_digits", 0)),
                    maximum_fraction_digits=int(payload.get("max_digits", 3)),
                ),
            }
        if kind == "plural":
            key = str(payload.get("key") or "plural.note")
            count = value if isinstance(value, int) and not isinstance(value, bool) else 0
            return {"kind": kind, "value": pluralize(key, count, locale=locale)}
        if kind in {"date", "datetime"}:
            text = str(value or "")
            if kind == "date":
                return {"kind": kind, "value": format_date(text, locale=locale)}
            return {"kind": kind, "value": format_datetime(text, locale=locale)}
        if kind == "relative":
            return {
                "kind": kind,
                "value": format_relative_time(
                    str(value or ""),
                    locale=locale,
                    now=datetime.now(timezone.utc),
                ),
            }
        raise ValueError(f"Unsupported format kind: {kind}")

    def rtl(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return RTL helper results for text or element data."""
        locale = str(payload.get("locale") or "en")
        text = str(payload.get("text") or "")
        nodes = nodes_from_payload(payload.get("nodes") or [])
        return {
            "locale": locale,
            "text": text,
            "warnings": bidi_warnings(text, locale=locale),
            "isolated": isolate_text(text),
            "mirrored": mirror_text(text, locale=locale),
            "css_vars": direction_css_vars(locale, override=payload.get("direction")),
            "tree": analyze_rtl_tree(nodes, locale=locale) if nodes else None,
        }

    def themes(self) -> dict[str, Any]:
        """Return theme registry options and validation."""
        return {
            "themes": [theme_summary(theme) for theme in self._theme_definitions()],
            "options": self._themes.options(),
            "validation": self._themes.validate(),
            "css": themes_css(),
        }

    def _theme_definitions(self) -> list[ThemeDefinition]:
        return [self._themes.get(name) or BUILTIN_THEMES[name] for name in self._themes.names]

    def theme_detail(self, name: str) -> dict[str, Any]:
        """Return one theme with contrast validation."""
        theme = self._themes.require(name)
        result = validate_theme(theme)
        return {
            "theme": theme.as_dict(),
            "summary": theme_summary(theme),
            "contrast": result.as_dict(),
            "issue_summary": theme_issue_summary(result),
            "grid": contrast_grid(theme),
            "css": theme_css(theme, selector=f'[data-a11y-theme="{theme.name}"]'),
        }

    def theme_create(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Create a theme from a payload without registering it."""
        return theme_from_payload(payload).as_dict()

    def theme_css(self, name: str, *, selector: str = ":root") -> dict[str, Any]:
        """Return CSS for one theme."""
        theme = self._themes.require(name)
        return {"theme": name, "css": theme_css(theme, selector=selector)}

    def theme_compare(self, first: str, second: str) -> dict[str, Any]:
        """Compare two themes."""
        return theme_diff(self._themes.require(first), self._themes.require(second))

    def theme_contrast(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate theme contrast, optionally for a custom theme."""
        theme_payload = payload.get("theme")
        level = str(payload.get("level") or "AA")
        if isinstance(theme_payload, Mapping):
            result = validate_theme(theme_from_payload(theme_payload), level=level)
            return {
                "theme": result.as_dict(),
                "issues": theme_issue_summary(result),
            }
        names = payload.get("themes")
        selected: dict[str, ThemeDefinition]
        if isinstance(names, Sequence) and not isinstance(names, str):
            selected = {
                str(name): self._themes.require(str(name))
                for name in names
                if str(name) in self._themes
            }
        else:
            selected = {
                name: self._themes.get(name) or create_theme(name, name)
                for name in self._themes.names
            }
        return validate_themes(selected, level=level)

    def theme_fixes(self, name: str) -> dict[str, Any]:
        """Suggest and preview theme contrast fixes."""
        theme = self._themes.require(name)
        changes = suggest_theme_fixes(theme)
        fixed = apply_theme_fixes(theme)
        return {
            "theme": name,
            "changes": changes,
            "before": theme_contrast_score(theme),
            "after": theme_contrast_score(fixed),
            "fixed_theme": fixed.as_dict(),
        }

    def preferences(self, profile: str = "default") -> dict[str, Any]:
        """Return effective preferences for a profile."""
        return self.preferences_service().effective(profile)

    def preferences_service(self) -> PreferenceService:
        """Return the preference service used by this facade."""
        return self._preferences

    def preferences_validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a preference payload."""
        return self._preferences.validate(payload)

    def preferences_update(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
    ) -> dict[str, Any]:
        """Update stored preferences."""
        return self._preferences.update(payload, profile=profile, now=_now()).as_dict()

    def preferences_replace(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
    ) -> dict[str, Any]:
        """Replace stored preferences."""
        return self._preferences.replace(payload, profile=profile).as_dict()

    def preferences_reset(self, *, profile: str = "default") -> dict[str, Any]:
        """Reset stored preferences."""
        return self._preferences.reset(profile=profile).as_dict()

    def preferences_defaults(self) -> dict[str, Any]:
        """Return default preferences."""
        return preference_defaults_payload()

    def preferences_schema(self) -> dict[str, Any]:
        """Return the preference field schema."""
        return preference_schema()

    def preferences_export(self, *, profile: str = "default") -> dict[str, Any]:
        """Export preferences from a profile."""
        return self._preferences.export(profile)

    def preferences_import(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
    ) -> dict[str, Any]:
        """Import preferences into a profile."""
        return self._preferences.import_record(payload, profile=profile).as_dict()

    def dashboard(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Build a combined accessibility dashboard payload."""
        locale = str(payload.get("locale") or "en")
        nodes = nodes_from_payload(payload.get("nodes") or [])
        audited = AccessibilityAuditor(locale=locale).audit(nodes)
        focus_report = analyze_focus_order(nodes)
        aria_report = validate_tree(nodes)
        theme = self._themes.require(str(payload.get("theme") or "graphite"))
        contrast_report = validate_theme(theme)
        return {
            "locale": locale,
            "direction": fallback_chain(locale)[0],
            "audit": audit_summary(audited),
            "focus": focus_summary(focus_report),
            "aria": aria_report.as_dict(),
            "contrast": theme_issue_summary(contrast_report),
            "preferences": self._preferences.current().as_dict(),
            "shortcuts": len(self._shortcuts),
            "themes": len(self._themes.names),
            "catalogs": len(self._catalogs.locales),
        }


__all__ = [
    "A11yService",
    "CatalogManager",
    "MessageCatalog",
    "PreferenceIssue",
    "PreferenceService",
    "ShortcutRegistry",
    "ThemeRegistry",
    "default_preferences",
    "export_preferences",
    "import_preferences",
    "validate_preferences",
]
