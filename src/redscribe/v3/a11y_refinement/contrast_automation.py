"""Automated contrast checks and repairs for V3 surfaces and themes.

All measurement and color math delegates to the V2 contrast primitives; this
module adds target discovery, batch automation, minimal-diff repairs, and
light/dark theme equivalence reporting.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.a11y.contrast import (
    contrast_ratio,
    distance_between_colors,
    parse_color,
    suggest_background,
    suggest_foreground,
)
from redscribe.v2.a11y.models import ThemeDefinition, WcagLevel
from redscribe.v3.a11y_refinement.models import (
    ContrastAutomationReport,
    ContrastFix,
    ContrastTarget,
)

PAIR_DEFINITIONS: tuple[tuple[str, str, str, bool], ...] = (
    ("body.text", "text", "surface", False),
    ("body.muted", "muted", "surface", False),
    ("action.accent", "accent", "surface", False),
    ("control.border", "border", "surface", True),
    ("focus.ring", "focus", "surface", True),
    ("inverse.text", "on_accent", "accent", False),
)

LIGHT_TOKENS: dict[str, str] = {
    "surface": "#ffffff",
    "text": "#1a1a1f",
    "muted": "#555566",
    "accent": "#1f5fbf",
    "border": "#8b8b99",
    "focus": "#005fcc",
    "on_accent": "#ffffff",
}

DARK_TOKENS: dict[str, str] = {
    "surface": "#141419",
    "text": "#f5f5f6",
    "muted": "#b0b0bf",
    "accent": "#8ab4ff",
    "border": "#7a7a88",
    "focus": "#9ec5ff",
    "on_accent": "#10121a",
}


def standard_targets(level: str | WcagLevel = WcagLevel.AA) -> tuple[ContrastTarget, ...]:
    """Return the standard contrast targets for both themes."""
    target_level = level if isinstance(level, WcagLevel) else WcagLevel(level.upper())
    targets: list[ContrastTarget] = []
    for theme_name, tokens in (("light", LIGHT_TOKENS), ("dark", DARK_TOKENS)):
        for name, foreground_key, background_key, graphical in PAIR_DEFINITIONS:
            targets.append(
                ContrastTarget(
                    name=f"{theme_name}.{name}",
                    foreground=tokens[foreground_key],
                    background=tokens[background_key],
                    graphical=graphical,
                    level=target_level,
                )
            )
    return tuple(targets)


def targets_from_theme(
    theme: ThemeDefinition,
    *,
    level: str | WcagLevel = WcagLevel.AA,
    prefix: str = "",
) -> tuple[ContrastTarget, ...]:
    """Derive contrast targets from one theme's token map."""
    target_level = level if isinstance(level, WcagLevel) else WcagLevel(level.upper())
    name = f"{prefix}." if prefix else ""
    targets: list[ContrastTarget] = []
    for pair_name, foreground_key, background_key, graphical in PAIR_DEFINITIONS:
        foreground = theme.token(foreground_key, "")
        background = theme.token(background_key, "")
        if not foreground or not background:
            continue
        targets.append(
            ContrastTarget(
                name=f"{name}{theme.name}.{pair_name}",
                foreground=foreground,
                background=background,
                graphical=graphical,
                level=target_level,
            )
        )
    return tuple(targets)


def targets_from_payload(
    payload: Mapping[str, Any],
    *,
    level: str | WcagLevel = WcagLevel.AA,
) -> tuple[ContrastTarget, ...]:
    """Build a target list from an API payload.

    Payloads may provide an explicit ``targets`` list or a flat ``palette``
    mapping where each entry supplies foreground and background tokens.
    """
    target_level = level if isinstance(level, WcagLevel) else WcagLevel(level.upper())
    raw_targets = payload.get("targets")
    result: list[ContrastTarget] = []
    if isinstance(raw_targets, Sequence) and not isinstance(raw_targets, (str, bytes)):
        for index, item in enumerate(raw_targets):
            if not isinstance(item, Mapping):
                continue
            foreground = item.get("foreground") or item.get("fg")
            background = item.get("background") or item.get("bg")
            if not isinstance(foreground, str) or not isinstance(background, str):
                continue
            result.append(
                ContrastTarget(
                    name=str(item.get("name") or f"target_{index + 1}"),
                    foreground=foreground,
                    background=background,
                    font_size=float(item.get("font_size") or 16.0),
                    bold=bool(item.get("bold", False)),
                    graphical=bool(item.get("graphical", False)),
                    level=target_level,
                )
            )
    if result:
        return tuple(result)
    palette = payload.get("palette")
    if isinstance(palette, Mapping):
        for key, value in palette.items():
            if not isinstance(value, Mapping):
                continue
            foreground = value.get("foreground") or value.get("fg")
            background = value.get("background") or value.get("bg") or "#ffffff"
            if not isinstance(foreground, str) or not isinstance(background, str):
                continue
            result.append(
                ContrastTarget(
                    name=str(key),
                    foreground=foreground,
                    background=background,
                    graphical=bool(value.get("graphical", False)),
                    level=target_level,
                )
            )
    if result:
        return tuple(result)
    return standard_targets(target_level)


def _required_ratio(target: ContrastTarget) -> float:
    """Return the WCAG ratio required for a target's context and level."""
    large = target.font_size >= 24.0 or (target.bold and target.font_size >= 18.66)
    if target.graphical:
        return 3.0
    if large:
        return 4.5 if target.level == WcagLevel.AAA else 3.0
    return 7.0 if target.level == WcagLevel.AAA else 4.5


def evaluate_target(target: ContrastTarget) -> dict[str, Any]:
    """Measure a target and return a JSON-safe pair record."""
    ratio = contrast_ratio(target.foreground, target.background)
    large = target.font_size >= 24.0 or (target.bold and target.font_size >= 18.66)
    required = _required_ratio(target)
    return {
        "name": target.name,
        "foreground": target.foreground,
        "background": target.background,
        "ratio": round(ratio, 3),
        "required": required,
        "passed": ratio >= required,
        "large_text": large,
        "graphical": target.graphical,
        "level": target.level.value,
    }


def auto_fix(target: ContrastTarget) -> ContrastFix:
    """Compute the smallest accessible change for a failing target."""
    required = _required_ratio(target)
    current = contrast_ratio(target.foreground, target.background)
    foreground = suggest_foreground(target.background, minimum=required)
    background = suggest_background(target.foreground, minimum=required)
    front_ratio = contrast_ratio(foreground, target.background)
    back_ratio = contrast_ratio(target.foreground, background)
    if front_ratio <= back_ratio:
        return ContrastFix(
            name=target.name,
            before_ratio=current,
            after_ratio=front_ratio,
            required=required,
            foreground=foreground.to_hex(),
            background=target.background,
            direction="foreground",
        )
    return ContrastFix(
        name=target.name,
        before_ratio=current,
        after_ratio=back_ratio,
        required=required,
        foreground=target.foreground,
        background=background.to_hex(),
        direction="background",
    )


def _distance(target: ContrastTarget, fix: ContrastFix) -> float:
    if fix.direction == "foreground":
        return distance_between_colors(target.foreground, fix.foreground)
    return distance_between_colors(target.background, fix.background)


def automate(
    targets: Sequence[ContrastTarget],
    *,
    repair: bool = True,
) -> ContrastAutomationReport:
    """Evaluate targets and optionally propose minimal repairs."""
    pairs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    fixes: list[ContrastFix] = []
    suggestions: list[str] = []
    for target in targets:
        record = evaluate_target(target)
        pairs.append(record)
        if record["passed"]:
            continue
        failures.append(record)
        candidate = auto_fix(target)
        if repair:
            fixes.append(candidate)
        replacement = (
            candidate.foreground if candidate.direction == "foreground" else candidate.background
        )
        suggestions.append(f"{target.name}: set {candidate.direction} to {replacement}")
    passed_count = len(pairs) - len(failures)
    score = (passed_count / len(pairs) * 100.0) if pairs else 100.0
    level = targets[0].level if targets else WcagLevel.AA
    distances = {target.name: _distance(target, auto_fix(target)) for target in targets}
    fixes.sort(key=lambda item: distances.get(item.name, 1.0))
    return ContrastAutomationReport(
        pairs=tuple(pairs),
        failures=tuple(failures),
        fixes=tuple(fixes),
        suggestions=tuple(suggestions),
        level=level,
        score=score,
    )


def dual_theme_report(
    *,
    light: ThemeDefinition | None = None,
    dark: ThemeDefinition | None = None,
    level: str | WcagLevel = WcagLevel.AA,
) -> dict[str, Any]:
    """Compare automated contrast results for both themes."""
    from redscribe.v2.a11y.themes import create_theme

    light_theme = light or create_theme("light", "Light", tokens=dict(LIGHT_TOKENS))
    dark_theme = dark or create_theme("graphite", "Graphite", mode="dark", tokens=dict(DARK_TOKENS))
    light_report = automate(targets_from_theme(light_theme, level=level), repair=False)
    dark_report = automate(targets_from_theme(dark_theme, level=level), repair=False)
    for report, theme in ((light_report, light_theme), (dark_report, dark_theme)):
        prefix = f"{theme.name}."
        for group in (report.pairs, report.failures):
            for record in group:
                if record["name"].startswith(prefix):
                    record["name"] = record["name"][len(prefix) :]
    light_names = {item["name"] for item in light_report.failures}
    dark_names = {item["name"] for item in dark_report.failures}
    return {
        "light": light_report.as_dict(),
        "dark": dark_report.as_dict(),
        "equivalent": light_names == dark_names,
        "shared_failures": sorted(light_names & dark_names),
        "score": round((light_report.score + dark_report.score) / 2.0, 1),
        "passed": light_report.passed and dark_report.passed,
    }


def parse_target_color(value: str) -> str:
    """Normalize a color string to canonical hex using the V2 parser."""
    return parse_color(value).to_hex()


__all__ = [
    "DARK_TOKENS",
    "LIGHT_TOKENS",
    "PAIR_DEFINITIONS",
    "auto_fix",
    "automate",
    "dual_theme_report",
    "evaluate_target",
    "parse_target_color",
    "standard_targets",
    "targets_from_payload",
    "targets_from_theme",
]
