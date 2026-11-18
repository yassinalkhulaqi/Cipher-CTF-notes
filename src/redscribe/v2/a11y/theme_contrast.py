"""Theme contrast validation and accessible color adjustment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.a11y.contrast import (
    Color,
    check_pair,
    coerce_color,
    contrast_ratio,
    distance_between_colors,
    parse_color,
    suggest_background,
    suggest_foreground,
)
from redscribe.v2.a11y.models import (
    ContrastPair,
    ContrastReport,
    Severity,
    ThemeDefinition,
    ThemeValidationIssue,
    WcagLevel,
    coerce_wcag_level,
)
from redscribe.v2.a11y.themes import missing_tokens

DEFAULT_COMBINATIONS: tuple[tuple[str, str, bool], ...] = (
    ("text", "surface", False),
    ("text", "surface_alt", False),
    ("text", "surface_raised", False),
    ("text_muted", "surface", False),
    ("text_muted", "surface_alt", False),
    ("text_subtle", "surface", False),
    ("accent", "surface", False),
    ("on_accent", "accent", False),
    ("success", "surface", False),
    ("warning", "surface", False),
    ("danger", "surface", False),
    ("info", "surface", False),
    ("border", "surface", True),
    ("border_strong", "surface_alt", True),
    ("focus", "surface", True),
)

STATUS_TOKENS: frozenset[str] = frozenset({"success", "warning", "danger", "info"})


@dataclass(frozen=True, slots=True)
class ThemeContrastResult:
    """Contrast validation result for one theme."""

    theme: str
    report: ContrastReport
    issues: tuple[ThemeValidationIssue, ...]
    suggestions: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "report": self.report.as_dict(),
            "issues": [issue.as_dict() for issue in self.issues],
            "suggestions": list(self.suggestions),
            "passed": self.passed,
        }


def theme_pairs(
    theme: ThemeDefinition,
    *,
    level: str | WcagLevel = WcagLevel.AA,
    combinations: Sequence[tuple[str, str, bool]] | None = None,
    font_size: float = 16.0,
) -> list[ContrastPair]:
    """Build all configured contrast pairs for a theme."""
    pairs: list[ContrastPair] = []
    for foreground, background, graphical in combinations or DEFAULT_COMBINATIONS:
        front = theme.token(foreground)
        back = theme.token(background)
        if not front or not back:
            continue
        pairs.append(
            check_pair(
                f"{foreground}_on_{background}",
                front,
                back,
                font_size=font_size,
                level=level,
                graphical=graphical,
            )
        )
    return pairs


def validate_theme(
    theme: ThemeDefinition,
    *,
    level: str | WcagLevel = WcagLevel.AA,
    font_size: float = 16.0,
    combinations: Sequence[tuple[str, str, bool]] | None = None,
) -> ThemeContrastResult:
    """Validate one theme's contrast and token completeness."""
    pairs = theme_pairs(theme, level=level, combinations=combinations, font_size=font_size)
    report = ContrastReport(
        pairs=tuple(pairs),
        failures=tuple(pair for pair in pairs if not pair.passed),
        score=sum(1 for pair in pairs if pair.passed) / len(pairs) * 100.0 if pairs else 100.0,
        target=coerce_wcag_level(level),
        suggestions=tuple(
            f"{pair.name}: try "
            f"{suggest_foreground(pair.background, minimum=pair.required).to_hex()}"
            for pair in pairs
            if not pair.passed
        ),
    )
    issues: list[ThemeValidationIssue] = []
    for name in missing_tokens(theme):
        issues.append(
            ThemeValidationIssue(
                theme=theme.name,
                token=name,
                message=f"Missing required token {name}",
                severity=Severity.SERIOUS,
            )
        )
    for pair in report.failures:
        issues.append(
            ThemeValidationIssue(
                theme=theme.name,
                token=pair.name.split("_on_", 1)[0],
                message=f"{pair.name} has contrast {pair.ratio:.2f}, needs {pair.required}",
                severity=Severity.MODERATE if pair.ratio >= 3.0 else Severity.SERIOUS,
                ratio=pair.ratio,
                required=pair.required,
            )
        )
    suggestions = list(report.suggestions)
    for name in missing_tokens(theme):
        suggestions.append(f"Define {name} in theme {theme.name}")
    return ThemeContrastResult(
        theme=theme.name,
        report=report,
        issues=tuple(issues),
        suggestions=tuple(suggestions),
    )


def validate_themes(
    themes: Mapping[str, ThemeDefinition],
    *,
    level: str | WcagLevel = WcagLevel.AA,
) -> dict[str, Any]:
    """Validate several themes and return aggregate results."""
    results = {name: validate_theme(theme, level=level) for name, theme in sorted(themes.items())}
    all_issues = [issue for result in results.values() for issue in result.issues]
    scores = [result.report.score for result in results.values()]
    return {
        "target": coerce_wcag_level(level).value,
        "themes": {name: result.as_dict() for name, result in results.items()},
        "passed": not all_issues,
        "issues": len(all_issues),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 100.0,
        "worst": min(scores) if scores else 100.0,
    }


def suggest_theme_fixes(
    theme: ThemeDefinition,
    *,
    minimum: float = 4.5,
    max_changes: int = 8,
) -> dict[str, str]:
    """Suggest token replacements that satisfy contrast minimums."""
    changes: dict[str, str] = {}
    for pair in theme_pairs(theme):
        if pair.passed or pair.name in changes:
            continue
        foreground, background = pair.name.split("_on_", 1)
        front = theme.token(foreground)
        back = theme.token(background)
        if not front or not back or len(changes) >= max_changes:
            continue
        replacement = suggest_foreground(back, minimum=pair.required)
        changes[foreground] = replacement.to_hex()
    return changes


def apply_theme_fixes(theme: ThemeDefinition, *, minimum: float = 4.5) -> ThemeDefinition:
    """Apply suggested contrast fixes to a theme."""
    fixes = suggest_theme_fixes(theme, minimum=minimum)
    tokens = dict(theme.tokens)
    tokens.update(fixes)
    return ThemeDefinition(
        name=theme.name,
        label=theme.label,
        mode=theme.mode,
        tokens=tokens,
        description=theme.description,
        extends=theme.extends,
        accent_hue=theme.accent_hue,
    )


def contrast_grid(
    theme: ThemeDefinition, *, token_names: Sequence[str] | None = None
) -> dict[str, Any]:
    """Build a contrast grid for selected theme tokens."""
    names = list(
        token_names or ("text", "text_muted", "accent", "success", "warning", "danger", "info")
    )
    rows: dict[str, dict[str, float]] = {}
    for foreground in names:
        front = theme.token(foreground)
        if not front:
            continue
        rows[foreground] = {}
        for background in names:
            back = theme.token(background)
            if not back:
                continue
            rows[foreground][background] = round(contrast_ratio(front, back), 2)
    return {
        "theme": theme.name,
        "tokens": names,
        "ratios": rows,
    }


def _parse_color_safely(value: str) -> Color | None:
    try:
        return parse_color(value)
    except ValueError:
        return None


def invalid_colors(theme: ThemeDefinition) -> dict[str, str]:
    """Return tokens whose color values cannot be parsed."""
    result: dict[str, str] = {}
    for name, value in sorted(theme.tokens.items()):
        if _parse_color_safely(value) is None:
            result[name] = value
    return result


def relative_color_distance(first: ThemeDefinition, second: ThemeDefinition) -> float:
    """Return the average color distance for shared theme tokens."""
    shared = set(first.tokens) & set(second.tokens)
    if not shared:
        return 1.0
    total = 0.0
    for name in sorted(shared):
        total += distance_between_colors(first.tokens[name], second.tokens[name])
    return total / len(shared)


def theme_contrast_score(theme: ThemeDefinition) -> float:
    """Return a 0-100 contrast score for a theme."""
    return validate_theme(theme).report.score


def accessible_status_colors(background: str, *, minimum: float = 4.5) -> dict[str, str]:
    """Suggest status colors that meet a minimum contrast on a background."""
    base_colors = {
        "success": "#7ee2a8",
        "warning": "#ffcf70",
        "danger": "#ff8f8f",
        "info": "#91c9ff",
    }
    result: dict[str, str] = {}
    for name, value in base_colors.items():
        if contrast_ratio(value, background) >= minimum:
            result[name] = value
            continue
        foreground = parse_color(value)
        back = coerce_color(background)
        for amount in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            adjusted = (
                foreground.darkened(amount)
                if back.luminance > 0.4
                else foreground.lightened(amount)
            )
            if contrast_ratio(adjusted, back) >= minimum:
                result[name] = adjusted.to_hex()
                break
        else:
            result[name] = suggest_foreground(back, minimum=minimum).to_hex()
    return result


def readable_background(foreground: str, *, minimum: float = 4.5) -> str:
    """Return an accessible background for a foreground color."""
    return suggest_background(foreground, minimum=minimum).to_hex()


def contrast_checks_from_payload(payload: Mapping[str, Any]) -> list[tuple[str, str, bool]]:
    """Parse custom contrast combination definitions from API input."""
    result: list[tuple[str, str, bool]] = []
    for entry in payload.get("combinations") or []:
        if isinstance(entry, str) and "_on_" in entry:
            front, back = entry.split("_on_", 1)
            result.append((front, back, False))
        elif isinstance(entry, Mapping):
            front = str(entry.get("foreground") or "")
            back = str(entry.get("background") or "")
            if front and back:
                result.append((front, back, bool(entry.get("graphical", False))))
    return result


def theme_issue_summary(result: ThemeContrastResult) -> dict[str, Any]:
    """Return a compact issue summary for a theme validation result."""
    by_severity: dict[str, int] = {}
    for issue in result.issues:
        by_severity[issue.severity.value] = by_severity.get(issue.severity.value, 0) + 1
    return {
        "theme": result.theme,
        "passed": result.passed,
        "score": round(result.report.score, 1),
        "issues": len(result.issues),
        "by_severity": dict(sorted(by_severity.items())),
        "checked": len(result.report.pairs),
    }
