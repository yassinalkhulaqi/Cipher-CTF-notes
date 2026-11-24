"""Facade coordinating the V3 accessibility, i18n, and theme refinements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.a11y.models import WcagLevel
from redscribe.v3.a11y_refinement.contrast_automation import (
    automate,
    dual_theme_report,
    targets_from_payload,
)
from redscribe.v3.a11y_refinement.formatting import (
    FORMAT_KINDS,
    catalog_report,
    format_batch,
    format_value,
    locale_profiles,
    round_trip,
    translate,
)
from redscribe.v3.a11y_refinement.keyboard_map import (
    V3_SHORTCUTS,
    bindings_for_group,
    export_keyboard_map,
    find_binding,
    focus_sequence,
    help_lines,
)
from redscribe.v3.a11y_refinement.models import (
    FormatRequest,
    MotionMode,
    SurfaceSpec,
    SyncStrategy,
)
from redscribe.v3.a11y_refinement.preferences import (
    PreferenceSyncService,
    motion_equivalence,
)
from redscribe.v3.a11y_refinement.rtl_layout import (
    bidi_report,
    document_attributes,
    layout_for,
    layout_manifest,
    pane_names,
    validate_layout,
)
from redscribe.v3.a11y_refinement.wcag22_rules import (
    WCAG22_RULES,
    audit_surface,
    audit_surfaces,
    summarize_runs,
)

DEFAULT_SURFACES: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(name="command-center", label="Command center", tiles=("rail", "activity")),
    SurfaceSpec(name="finding-studio", label="Finding studio", target_size=28),
    SurfaceSpec(name="evidence-lab", label="Evidence lab", target_size=28),
    SurfaceSpec(
        name="graph-workbench",
        label="Graph workbench",
        non_text_contrast=2.6,
        drag_only=True,
    ),
    SurfaceSpec(name="search-intelligence", label="Search intelligence", repeated_entry=True),
    SurfaceSpec(name="playbook-automation", label="Playbook automation"),
    SurfaceSpec(name="report-designer", label="Report designer", hover_content=True),
    SurfaceSpec(name="timeline", label="Activity timeline"),
    SurfaceSpec(name="sync", label="Sync and portability", auth_captcha="captcha"),
    SurfaceSpec(name="security", label="Security vault", level=WcagLevel.AAA),
    SurfaceSpec(name="performance", label="Performance HUD", focus_indicator_width=1),
    SurfaceSpec(
        name="a11y-refinement",
        label="Accessibility refinement",
        screen_reader_labels=True,
    ),
)


@dataclass(slots=True)
class A11yRefinementService:
    """Application service used by the V3 a11y namespace."""

    _surfaces: dict[str, SurfaceSpec] = field(default_factory=dict)
    _preferences: PreferenceSyncService = field(default_factory=PreferenceSyncService)

    def __post_init__(self) -> None:
        for spec in DEFAULT_SURFACES:
            self._surfaces.setdefault(spec.name, spec)

    @property
    def preference_service(self) -> PreferenceSyncService:
        """Return the cross-feature preference service."""
        return self._preferences

    def surface_names(self) -> tuple[str, ...]:
        """Return registered surfaces in stable order."""
        return tuple(sorted(self._surfaces))

    def register_surface(self, spec: SurfaceSpec) -> SurfaceSpec:
        """Register or replace a surface specification."""
        self._surfaces[spec.name] = spec
        return spec

    def surface(self, name: str) -> SurfaceSpec:
        """Return one surface or raise a clear error."""
        spec = self._surfaces.get(name)
        if spec is None:
            raise ValueError(f"Unknown surface: {name}")
        return spec

    def health(self) -> dict[str, Any]:
        """Report namespace capabilities and default settings."""
        return {
            "namespace": "a11y",
            "version": "3.0",
            "surfaces": len(self._surfaces),
            "wcag22_rules": len(WCAG22_RULES),
            "v3_shortcuts": len(V3_SHORTCUTS),
            "panes": len(pane_names()),
            "format_kinds": list(FORMAT_KINDS),
            "locales": len(locale_profiles()),
            "levels": [level.value for level in WcagLevel],
            "strategies": [item.value for item in SyncStrategy],
            "motions": [item.value for item in MotionMode],
        }

    def audit(self, name: str, *, level: str | None = None) -> dict[str, Any]:
        """Audit one registered surface."""
        return audit_surface(self.surface(name), level=level).as_dict()

    def audit_all(self, *, level: str | None = None) -> dict[str, Any]:
        """Audit all registered surfaces and return a summary."""
        runs = audit_surfaces(tuple(self._surfaces.values()), level=level)
        summary = summarize_runs(runs)
        return {
            **summary,
            "runs": [run.as_dict() for run in runs],
        }

    def wcag_rules(self, *, level: str = "AAA") -> dict[str, Any]:
        """Return the WCAG 2.2 rule catalog."""
        from redscribe.v3.a11y_refinement.wcag22_rules import rules_for_level

        normalized = level.upper()
        selected = rules_for_level(normalized)
        return {
            "level": normalized,
            "count": len(selected),
            "rules": [rule.as_dict() for rule in selected],
        }

    def contrast(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Run an automated contrast pass."""
        targets = targets_from_payload(payload)
        report = automate(targets, repair=bool(payload.get("repair", True)))
        return report.as_dict()

    def dual_theme(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Compare light and dark theme contrast results."""
        return dual_theme_report(level=str((payload or {}).get("level") or "AA"))

    def format_one(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Format a single value."""
        request = FormatRequest(
            locale=str(payload.get("locale") or "en"),
            kind=str(payload.get("kind") or "number"),
            value=payload.get("value"),
            options=dict(payload.get("options") or {}),
        )
        return format_value(request).as_dict()

    def format_many(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Format a batch of values."""
        raw = payload.get("requests") or ()
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError("'requests' must be a list")
        requests: list[FormatRequest] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            requests.append(
                FormatRequest(
                    locale=str(item.get("locale") or "en"),
                    kind=str(item.get("kind") or "number"),
                    value=item.get("value"),
                    options=dict(item.get("options") or {}),
                )
            )
        return {"results": [result.as_dict() for result in format_batch(requests)]}

    def translation(
        self, locale: str, key: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Translate one V3 message key."""
        return translate(locale, key, params)

    def locales(self, *, accept_language: str = "") -> dict[str, Any]:
        """Return locale profiles, catalog coverage, and language matching."""
        from redscribe.v2.a11y.i18n.locales import best_match_header

        available = tuple(item["value"] for item in locale_profiles())
        return {
            "locales": list(locale_profiles()),
            "catalogs": catalog_report(),
            "matched": best_match_header(accept_language, available) if accept_language else "",
        }

    def round_trip(self, value: int | float, locale: str, digits: int) -> dict[str, Any]:
        """Verify number formatting round-trips for a locale."""
        return round_trip(value, locale, digits=digits)

    def rtl(self, pane: str, locale: str, *, text: str = "", override: str = "") -> dict[str, Any]:
        """Return RTL layout metadata for one pane."""
        layout = layout_for(pane, locale, override=override or None, text=text)
        return {
            "layout": layout.as_dict(),
            "validation": validate_layout(layout),
            "attributes": document_attributes(locale, override=override or None),
        }

    def rtl_manifest(self, locale: str, *, override: str = "") -> dict[str, Any]:
        """Return layout metadata for every pane."""
        return layout_manifest(locale, override=override or None)

    def bidi(self, text: str, locale: str, *, override: str = "") -> dict[str, Any]:
        """Check one text fragment for bidirectional hazards."""
        return bidi_report(text, locale, override=override or None)

    def keyboard(
        self,
        *,
        locale: str = "en",
        platform: str = "desktop",
        overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Export the complete keyboard map."""
        return export_keyboard_map(locale=locale, platform=platform, overrides=overrides).as_dict()

    def keyboard_help(self, *, locale: str, platform: str) -> dict[str, Any]:
        """Return localized keyboard help and focus order."""
        keyboard_map = export_keyboard_map(locale=locale, platform=platform)
        return {
            "lines": list(help_lines(keyboard_map, locale=locale)),
            "focus_order": list(focus_sequence(keyboard_map)),
            "groups": {key: list(value) for key, value in keyboard_map.groups.items()},
        }

    def keyboard_lookup(
        self,
        pressed: Sequence[str],
        *,
        scope: str,
        locale: str,
        platform: str,
    ) -> dict[str, Any]:
        """Resolve one key press against the exported map."""
        keyboard_map = export_keyboard_map(locale=locale, platform=platform)
        matches = find_binding(keyboard_map, pressed, scope=scope)
        return {"bindings": [item.as_dict() for item in matches]}

    def keyboard_group(self, group: str, *, locale: str, platform: str) -> dict[str, Any]:
        """Return all bindings in a help group."""
        keyboard_map = export_keyboard_map(locale=locale, platform=platform)
        return {
            "group": group,
            "bindings": [item.as_dict() for item in bindings_for_group(keyboard_map, group)],
        }

    def preferences(self, *, profile: str = "default") -> dict[str, Any]:
        """Return effective preferences and appearance."""
        return self._preferences.effective(profile)

    def preferences_update(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
    ) -> dict[str, Any]:
        """Update a preference profile."""
        return self._preferences.update(payload, profile=profile).as_dict()

    def preferences_sync(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
        strategy: SyncStrategy = SyncStrategy.MERGE,
    ) -> dict[str, Any]:
        """Synchronize a remote preference record."""
        return self._preferences.sync(payload, profile=profile, strategy=strategy).as_dict()

    def motion(self, mode: str) -> dict[str, Any]:
        """Return motion-mode equivalence metadata."""
        return motion_equivalence(mode)

    def dashboard(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Build a combined refinement dashboard payload."""
        body = dict(payload or {})
        locale = str(body.get("locale") or "en")
        audit = self.audit_all(level=str(body.get("level") or "AA"))
        keyboard_map = export_keyboard_map(locale=locale, platform="desktop")
        preferences = self._preferences.effective(str(body.get("profile") or "default"))
        return {
            "locale": locale,
            "direction": layout_manifest(locale)["direction"],
            "audit": {key: value for key, value in audit.items() if key != "runs"},
            "surfaces": self.surface_names(),
            "contrast": self.dual_theme(body).get("score", 0.0),
            "keyboard": {
                "bindings": len(keyboard_map.bindings),
                "groups": sorted(keyboard_map.groups),
                "complete": keyboard_map.complete,
            },
            "catalogs": catalog_report()["per_locale"],
            "preferences": preferences,
            "motion": motion_equivalence(str(body.get("motion") or "full")),
        }

    def export(self) -> dict[str, Any]:
        """Export all refinement metadata as one portable payload."""
        return {
            "version": "3.0",
            "surfaces": [spec.as_dict() for spec in self._surfaces.values()],
            "rules": [rule.as_dict() for rule in WCAG22_RULES],
            "panes": list(pane_names()),
            "shortcuts": [item[0] for item in V3_SHORTCUTS],
            "locales": list(locale_profiles()),
            "keyboard": export_keyboard_map().as_dict(),
        }


__all__ = ["DEFAULT_SURFACES", "A11yRefinementService"]
