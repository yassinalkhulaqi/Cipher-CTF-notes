"""RTL layout metadata for every V3 pane.

The V2 RTL helpers handle individual strings. This module describes complete
panes with logical regions, mirrored icons, and CSS variables so that a locale
switch flips an entire workbench without changing component structure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.a11y.i18n.rtl import (
    bidi_warnings,
    direction_css_vars,
    document_direction,
    is_rtl_locale,
    logical_side,
    mirror_text,
    physical_side,
)
from redscribe.v3.a11y_refinement.formatting import locale_direction
from redscribe.v3.a11y_refinement.models import PaneLayout, SurfaceSpec

MIRRORED_ICONS: tuple[str, ...] = (
    "chevron-left",
    "chevron-right",
    "arrow-left",
    "arrow-right",
    "back",
    "forward",
    "indent",
    "outdent",
    "sidebar-toggle",
    "panel-toggle",
)

STATIC_ICONS: tuple[str, ...] = (
    "search",
    "save",
    "settings",
    "close",
    "check",
    "warning",
    "info",
    "filter",
    "sort",
)

PANE_REGIONS: dict[str, tuple[str, ...]] = {
    "command-center": ("rail", "activity", "quick-actions", "metrics"),
    "finding-studio": ("list", "editor", "cvss", "remediation"),
    "evidence-lab": ("table", "preview", "hex", "custody"),
    "graph-workbench": ("toolbar", "canvas", "inspector", "legend"),
    "search-intelligence": ("query", "facets", "results", "cluster"),
    "playbook-automation": ("templates", "steps", "variables", "trace"),
    "report-designer": ("outline", "page", "theme", "appendix"),
    "timeline": ("filters", "stream", "detail", "pagination"),
    "sync": ("sources", "preview", "conflicts", "progress"),
    "security": ("risks", "audit", "redaction", "keys"),
    "performance": ("hud", "budgets", "fixtures", "plans"),
    "a11y-refinement": ("audit", "contrast", "keyboard", "preferences"),
}


def pane_names() -> tuple[str, ...]:
    """Return all panes that have RTL metadata."""
    return tuple(sorted(PANE_REGIONS))


def resolve_direction(locale: str, override: str | None = None) -> str:
    """Resolve the layout direction for a locale and optional user override."""
    if override and override.strip().lower() in {"ltr", "rtl"}:
        return override.strip().lower()
    return locale_direction(locale)


def sides_for(direction: str) -> dict[str, str]:
    """Map logical sides to physical sides for a direction."""
    locale = "ar" if direction == "rtl" else "en"
    return {
        "start": physical_side("start", locale=locale),
        "end": physical_side("end", locale=locale),
        "top": "top",
        "bottom": "bottom",
    }


def css_variables(locale: str, *, override: str | None = None) -> dict[str, str]:
    """Return direction CSS variables plus V3 layout variables."""
    direction = resolve_direction(locale, override)
    variables = direction_css_vars(locale, override=direction)
    variables.update(
        {
            "--v3-dir": direction,
            "--v3-inline-start": variables["--a11y-inline-start"],
            "--v3-inline-end": variables["--a11y-inline-end"],
            "--v3-text-align": variables["--a11y-text-align"],
            "--v3-panel-order": "rtl" if direction == "rtl" else "ltr",
        }
    )
    return variables


def mirrored_icons(direction: str) -> tuple[str, ...]:
    """Return icons that must flip for the given direction."""
    return MIRRORED_ICONS if direction == "rtl" else ()


def order_regions(regions: Sequence[str], direction: str) -> tuple[str, ...]:
    """Order pane regions for a direction while keeping focus order logical."""
    values = tuple(regions)
    return tuple(reversed(values)) if direction == "rtl" else values


def layout_for(
    pane: str,
    locale: str,
    *,
    override: str | None = None,
    text: str = "",
) -> PaneLayout:
    """Build layout metadata for one pane."""
    regions = PANE_REGIONS.get(pane, ("content",))
    direction = resolve_direction(locale, override)
    warnings: list[str] = []
    if text:
        warnings.extend(bidi_warnings(text, locale=locale))
    if direction == "rtl" and any(icon in STATIC_ICONS for icon in regions):
        warnings.append("static icons in reversed panes must not be mirrored")
    return PaneLayout(
        pane=pane,
        direction=direction,
        css_class=f"v3-rtl-{direction}",
        sides=sides_for(direction),
        mirror_icons=mirrored_icons(direction),
        ordered_regions=order_regions(regions, direction),
        warnings=tuple(warnings),
    )


def layout_manifest(
    locale: str,
    *,
    override: str | None = None,
    panes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return metadata for all panes in one locale."""
    selected = tuple(panes) if panes is not None else pane_names()
    layouts = [layout_for(pane, locale, override=override) for pane in selected]
    direction = resolve_direction(locale, override)
    return {
        "locale": locale,
        "direction": direction,
        "rtl": direction == "rtl",
        "css": css_variables(locale, override=override),
        "regions": list(order_regions(tuple(PANE_REGIONS), direction)),
        "panes": [item.as_dict() for item in layouts],
        "static_icons": list(STATIC_ICONS),
        "mirrored_icons": list(mirrored_icons(direction)),
        "warnings": [warning for item in layouts for warning in item.warnings],
    }


def bidi_report(text: str, locale: str, *, override: str | None = None) -> dict[str, Any]:
    """Analyze one text fragment for bidirectional hazards."""
    direction = resolve_direction(locale, override)
    return {
        "locale": locale,
        "direction": direction,
        "rtl_locale": is_rtl_locale(locale),
        "warnings": bidi_warnings(text, locale=locale),
        "mirrored": mirror_text(text, locale=locale),
        "logical_left": logical_side("left", locale=locale),
        "logical_right": logical_side("right", locale=locale),
        "physical_start": physical_side("start", locale=locale),
        "physical_end": physical_side("end", locale=locale),
    }


def validate_layout(layout: PaneLayout) -> dict[str, Any]:
    """Check that a layout keeps a stable, logical focus order."""
    problems: list[str] = []
    if not layout.ordered_regions:
        problems.append("pane has no regions")
    if layout.direction == "rtl" and layout.sides.get("start") != "right":
        problems.append("RTL start side is not physical right")
    if layout.direction == "ltr" and layout.sides.get("start") != "left":
        problems.append("LTR start side is not physical left")
    if layout.css_class != f"v3-rtl-{layout.direction}":
        problems.append("unexpected direction class")
    return {
        "pane": layout.pane,
        "valid": not problems,
        "problems": problems,
        "regions": list(layout.ordered_regions),
    }


def surface_direction(spec: SurfaceSpec, *, override: str | None = None) -> str:
    """Resolve direction for an audited surface."""
    return resolve_direction(spec.locale, override)


def side_map(layout: PaneLayout) -> Mapping[str, str]:
    """Expose the physical side map of a layout."""
    return dict(layout.sides)


def document_attributes(locale: str, *, override: str | None = None) -> dict[str, str]:
    """Return the lang/dir attributes required on a V3 surface root."""
    return {
        "lang": locale,
        "dir": document_direction(locale, override=resolve_direction(locale, override)),
    }


__all__ = [
    "MIRRORED_ICONS",
    "PANE_REGIONS",
    "STATIC_ICONS",
    "bidi_report",
    "css_variables",
    "document_attributes",
    "layout_for",
    "layout_manifest",
    "mirrored_icons",
    "pane_names",
    "resolve_direction",
    "side_map",
    "sides_for",
    "surface_direction",
    "validate_layout",
]
