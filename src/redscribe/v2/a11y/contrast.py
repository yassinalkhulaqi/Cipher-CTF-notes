"""Color conversion, contrast calculation, and WCAG contrast validation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.a11y.models import (
    ContrastPair,
    ContrastReport,
    Severity,
    WcagLevel,
    coerce_wcag_level,
)

NAMED_COLORS: dict[str, str] = {
    "black": "#000000",
    "white": "#ffffff",
    "red": "#ff0000",
    "green": "#008000",
    "blue": "#0000ff",
    "yellow": "#ffff00",
    "cyan": "#00ffff",
    "magenta": "#ff00ff",
    "gray": "#808080",
    "grey": "#808080",
    "silver": "#c0c0c0",
    "maroon": "#800000",
    "olive": "#808000",
    "purple": "#800080",
    "teal": "#008080",
    "navy": "#000080",
    "orange": "#ffa500",
    "transparent": "#00000000",
}

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
RGB_RE = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})"
    r"(?:\s*,\s*(0|1|0?\.\d+))?\s*\)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Color:
    """An sRGB color with an optional alpha channel."""

    red: int
    green: int
    blue: int
    alpha: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.red <= 255:
            raise ValueError("red must be between 0 and 255")
        if not 0 <= self.green <= 255:
            raise ValueError("green must be between 0 and 255")
        if not 0 <= self.blue <= 255:
            raise ValueError("blue must be between 0 and 255")
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("alpha must be between 0 and 1")

    @property
    def channels(self) -> tuple[int, int, int]:
        return self.red, self.green, self.blue

    @property
    def luminance(self) -> float:
        channels = []
        for channel in self.channels:
            component = channel / 255.0
            if component <= 0.04045:
                channels.append(component / 12.92)
            else:
                channels.append(((component + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def with_alpha(self, alpha: float) -> Color:
        return Color(self.red, self.green, self.blue, alpha)

    def blended_over(self, background: Color) -> Color:
        factor = self.alpha
        inverse = 1.0 - factor
        return Color(
            round(self.red * factor + background.red * inverse),
            round(self.green * factor + background.green * inverse),
            round(self.blue * factor + background.blue * inverse),
            1.0,
        )

    def lightened(self, amount: float) -> Color:
        return _mix(self, Color(255, 255, 255), amount)

    def darkened(self, amount: float) -> Color:
        return _mix(self, Color(0, 0, 0), amount)

    def to_hex(self, *, include_alpha: bool = False) -> str:
        base = f"#{self.red:02x}{self.green:02x}{self.blue:02x}"
        if include_alpha and self.alpha < 1.0:
            return f"{base}{round(self.alpha * 255):02x}"
        return base

    def to_rgb(self) -> str:
        if self.alpha < 1.0:
            return f"rgba({self.red}, {self.green}, {self.blue}, {self.alpha:.2f})"
        return f"rgb({self.red}, {self.green}, {self.blue})"

    def as_dict(self) -> dict[str, Any]:
        return {
            "hex": self.to_hex(include_alpha=True),
            "rgb": self.to_rgb(),
            "luminance": round(self.luminance, 4),
            "alpha": self.alpha,
        }


def _mix(first: Color, second: Color, amount: float) -> Color:
    clamped = min(1.0, max(0.0, amount))
    return Color(
        round(first.red + (second.red - first.red) * clamped),
        round(first.green + (second.green - first.green) * clamped),
        round(first.blue + (second.blue - first.blue) * clamped),
        first.alpha,
    )


def parse_color(value: str) -> Color:
    """Parse hex, rgb, rgba, or common CSS names into a Color."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Color must be a non-empty string")
    text = value.strip().lower()
    if text in NAMED_COLORS:
        text = NAMED_COLORS[text]
    hex_match = HEX_RE.match(text)
    if hex_match:
        raw = hex_match.group(1)
        if len(raw) in (3, 4):
            expanded = "".join(char * 2 for char in raw)
            if len(expanded) == 8:
                return Color(
                    int(expanded[0:2], 16),
                    int(expanded[2:4], 16),
                    int(expanded[4:6], 16),
                    int(expanded[6:8], 16) / 255.0,
                )
            return Color(
                int(expanded[0:2], 16),
                int(expanded[2:4], 16),
                int(expanded[4:6], 16),
            )
        if len(raw) == 6:
            return Color(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
        if len(raw) == 8:
            return Color(
                int(raw[0:2], 16),
                int(raw[2:4], 16),
                int(raw[4:6], 16),
                int(raw[6:8], 16) / 255.0,
            )
        raise ValueError(f"Unsupported hex color: {value}")
    rgb_match = RGB_RE.match(text)
    if rgb_match:
        red, green, blue = (int(rgb_match.group(index)) for index in (1, 2, 3))
        alpha = float(rgb_match.group(4)) if rgb_match.group(4) is not None else 1.0
        return Color(red, green, blue, alpha)
    raise ValueError(f"Unsupported color format: {value}")


def coerce_color(value: str | Color) -> Color:
    """Return a Color from either a Color instance or a string."""
    if isinstance(value, Color):
        return value
    return parse_color(value)


def contrast_ratio(foreground: str | Color, background: str | Color) -> float:
    """Compute the WCAG contrast ratio between two colors."""
    front = coerce_color(foreground)
    back = coerce_color(background)
    if front.alpha < 1.0:
        front = front.blended_over(back)
    first = max(front.luminance, back.luminance)
    second = min(front.luminance, back.luminance)
    if second < 0.0:
        return 1.0
    return (first + 0.05) / (second + 0.05)


def is_large_text(font_size: float, bold: bool = False) -> bool:
    """Return whether text qualifies for the large-text contrast threshold."""
    return font_size >= 24.0 or (bold and font_size >= 18.66)


def required_ratio(
    level: str | WcagLevel = WcagLevel.AA,
    *,
    font_size: float = 16.0,
    bold: bool = False,
    large_text: bool | None = None,
    graphical: bool = False,
) -> float:
    """Return the minimum contrast ratio required for a context."""
    target = coerce_wcag_level(level)
    large = is_large_text(font_size, bold) if large_text is None else large_text
    if graphical:
        return 3.0
    if target == WcagLevel.A:
        return 3.0 if large else 4.5
    if target == WcagLevel.AA:
        return 3.0 if large else 4.5
    return 4.5 if large else 7.0


def grade_contrast(ratio: float, *, font_size: float = 16.0, bold: bool = False) -> dict[str, Any]:
    """Grade one contrast ratio against A, AA, and AAA thresholds."""
    normal = not is_large_text(font_size, bold)
    aa = 4.5 if normal else 3.0
    aaa = 7.0 if normal else 4.5
    grades = {
        "A": ratio >= 3.0,
        "AA": ratio >= aa,
        "AA Large": ratio >= 3.0,
        "AAA": ratio >= aaa,
    }
    if ratio >= aaa:
        best = "AAA"
    elif ratio >= aa:
        best = "AA"
    elif ratio >= 3.0:
        best = "A"
    else:
        best = "fail"
    return {"grades": grades, "best": best, "ratio": round(ratio, 2)}


def check_pair(
    name: str,
    foreground: str | Color,
    background: str | Color,
    *,
    font_size: float = 16.0,
    bold: bool = False,
    large_text: bool | None = None,
    level: str | WcagLevel = WcagLevel.AA,
    graphical: bool = False,
) -> ContrastPair:
    """Validate one foreground/background pair."""
    large = is_large_text(font_size, bold) if large_text is None else large_text
    required = required_ratio(
        level,
        font_size=font_size,
        bold=bold,
        large_text=large,
        graphical=graphical,
    )
    ratio = contrast_ratio(foreground, background)
    return ContrastPair(
        name=name,
        foreground=coerce_color(foreground).to_hex(include_alpha=True),
        background=coerce_color(background).to_hex(include_alpha=True),
        ratio=ratio,
        font_size=font_size,
        bold=bold,
        large_text=large,
        required=required,
        passed=ratio >= required,
        level=coerce_wcag_level(level),
    )


def suggest_foreground(
    background: str | Color,
    *,
    minimum: float = 4.5,
    prefer_light: bool | None = None,
) -> Color:
    """Find a nearby accessible foreground color for a background."""
    back = coerce_color(background)
    if back.alpha < 1.0:
        back = back.blended_over(Color(255, 255, 255))
    if prefer_light is None:
        prefer_light = back.luminance < 0.4
    start = Color(255, 255, 255) if prefer_light else Color(0, 0, 0)
    if contrast_ratio(start, back) >= minimum:
        return start
    for step in range(1, 101):
        amount = step / 100.0
        candidate = _mix(start, back, amount)
        if contrast_ratio(candidate, back) >= minimum:
            return candidate
    return (
        start
        if contrast_ratio(start, back) >= contrast_ratio(Color(0, 0, 0), back)
        else Color(0, 0, 0)
    )


def suggest_background(foreground: str | Color, *, minimum: float = 4.5) -> Color:
    """Find an accessible background color for a foreground color."""
    front = coerce_color(foreground)
    for candidate in (Color(255, 255, 255), Color(0, 0, 0)):
        if contrast_ratio(front, candidate) >= minimum:
            return candidate
    for step in range(1, 101):
        amount = step / 100.0
        for candidate in (Color(255, 255, 255), Color(0, 0, 0)):
            adjusted = _mix(candidate, front, amount)
            if contrast_ratio(front, adjusted) >= minimum:
                return adjusted
    return Color(255, 255, 255)


def _pair_from_mapping(name: str, payload: Mapping[str, Any]) -> ContrastPair:
    foreground = payload.get("foreground") or payload.get("fg") or payload.get("color")
    background = payload.get("background") or payload.get("bg") or "#ffffff"
    if not isinstance(foreground, str) or not isinstance(background, str):
        raise ValueError(f"{name} foreground and background must be strings")
    size = payload.get("font_size", 16.0)
    if isinstance(size, bool) or not isinstance(size, (int, float)):
        raise ValueError(f"{name} font_size must be a number")
    level = str(payload.get("level", "AA"))
    return check_pair(
        name,
        foreground,
        background,
        font_size=float(size),
        bold=bool(payload.get("bold", False)),
        large_text=payload.get("large_text")
        if isinstance(payload.get("large_text"), bool)
        else None,
        level=level,
        graphical=bool(payload.get("graphical", False)),
    )


def build_report(
    pairs: Sequence[ContrastPair] | Mapping[str, Mapping[str, Any]] | None = None,
    *,
    level: str | WcagLevel = WcagLevel.AA,
) -> ContrastReport:
    """Validate a sequence of pairs or a mapping of named pair definitions."""
    checked: list[ContrastPair] = []
    if pairs is None:
        pairs = {}
    if isinstance(pairs, Mapping):
        for name, payload in pairs.items():
            if not isinstance(payload, Mapping):
                raise ValueError(f"{name} must be an object")
            checked.append(_pair_from_mapping(str(name), payload))
    else:
        checked.extend(pairs)
    failures = tuple(pair for pair in checked if not pair.passed)
    score = 100.0 if not checked else (len(checked) - len(failures)) / len(checked) * 100.0
    suggestions: list[str] = []
    for pair in failures:
        replacement = suggest_foreground(pair.background, minimum=pair.required)
        suggestions.append(f"{pair.name}: use {replacement.to_hex()} instead of {pair.foreground}")
    return ContrastReport(
        pairs=tuple(checked),
        failures=failures,
        score=score,
        target=coerce_wcag_level(level),
        suggestions=tuple(suggestions),
    )


def palette_pairs(
    palette: Mapping[str, str],
    *,
    combinations: Sequence[tuple[str, str]] | None = None,
    font_size: float = 16.0,
    level: str | WcagLevel = WcagLevel.AA,
) -> list[ContrastPair]:
    """Build contrast pairs from a named color palette."""
    if combinations is None:
        combinations = (
            ("text", "surface"),
            ("text_muted", "surface"),
            ("text", "surface_alt"),
            ("accent", "surface"),
            ("on_accent", "accent"),
            ("border", "surface"),
        )
    result: list[ContrastPair] = []
    for foreground_key, background_key in combinations:
        foreground = palette.get(foreground_key)
        background = palette.get(background_key)
        if not foreground or not background:
            continue
        graphical = foreground_key == "border"
        result.append(
            check_pair(
                f"{foreground_key}_on_{background_key}",
                foreground,
                background,
                font_size=font_size,
                level=level,
                graphical=graphical,
            )
        )
    return result


def hue_rotate(color: str | Color, degrees: float) -> Color:
    """Rotate a color hue in HSL space."""
    source = coerce_color(color)
    red, green, blue = (channel / 255.0 for channel in source.channels)
    maximum = max(red, green, blue)
    minimum = min(red, green, blue)
    delta = maximum - minimum
    lightness = (maximum + minimum) / 2.0
    if delta == 0.0:
        hue = 0.0
        saturation = 0.0
    else:
        saturation = delta / (1.0 - abs(2.0 * lightness - 1.0))
        if maximum == red:
            hue = ((green - blue) / delta) % 6.0
        elif maximum == green:
            hue = (blue - red) / delta + 2.0
        else:
            hue = (red - green) / delta + 4.0
        hue = hue * 60.0
    new_hue = (hue + degrees) % 360.0
    chroma = (1.0 - abs(2.0 * lightness - 1.0)) * saturation
    intermediate = chroma * (1.0 - abs((new_hue / 60.0) % 2.0 - 1.0))
    match = lightness - chroma / 2.0
    if new_hue < 60.0:
        channels = (chroma, intermediate, 0.0)
    elif new_hue < 120.0:
        channels = (intermediate, chroma, 0.0)
    elif new_hue < 180.0:
        channels = (0.0, chroma, intermediate)
    elif new_hue < 240.0:
        channels = (0.0, intermediate, chroma)
    elif new_hue < 300.0:
        channels = (intermediate, 0.0, chroma)
    else:
        channels = (chroma, 0.0, intermediate)
    red, green, blue = channels
    return Color(
        round((red + match) * 255.0),
        round((green + match) * 255.0),
        round((blue + match) * 255.0),
        source.alpha,
    )


def contrast_grade_label(pair: ContrastPair) -> str:
    """Return a human-readable grade for a validated pair."""
    result = grade_contrast(
        pair.ratio,
        font_size=pair.font_size,
        bold=pair.bold,
    )
    return str(result["best"])


def summarize_report(
    report: ContrastReport, *, severity: Severity = Severity.MODERATE
) -> dict[str, Any]:
    """Summarize a contrast report for dashboard display."""
    return {
        "passed": report.passed,
        "score": round(report.score, 1),
        "checked": len(report.pairs),
        "failed": len(report.failures),
        "lowest": min((pair.ratio for pair in report.pairs), default=0.0),
        "severity": severity.value if report.failures else Severity.INFO.value,
        "target": report.target.value,
        "suggestions": list(report.suggestions[:5]),
    }


def relative_luminance(color: str | Color) -> float:
    """Return the WCAG relative luminance of a color."""
    return coerce_color(color).luminance


def distance_between_colors(first: str | Color, second: str | Color) -> float:
    """Return a normalized Euclidean distance between two colors."""
    left = coerce_color(first).channels
    right = coerce_color(second).channels
    total = sum((a - b) ** 2 for a, b in zip(left, right, strict=False))
    return math.sqrt(total) / (255.0 * math.sqrt(3.0))
