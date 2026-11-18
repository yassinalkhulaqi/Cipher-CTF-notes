"""Theme token definitions, inheritance, generation, and CSS emission."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.a11y.models import ThemeDefinition, ThemeToken

TOKEN_CATEGORIES: dict[str, str] = {
    "surface": "Background surfaces",
    "text": "Foreground text",
    "accent": "Accent and interactive colors",
    "border": "Dividers and outlines",
    "status": "Status colors",
    "motion": "Motion and focus settings",
}

REQUIRED_TOKENS: frozenset[str] = frozenset(
    {
        "surface",
        "surface_alt",
        "surface_raised",
        "text",
        "text_muted",
        "text_subtle",
        "accent",
        "accent_hover",
        "on_accent",
        "border",
        "border_strong",
        "focus",
        "success",
        "warning",
        "danger",
        "info",
    }
)

TOKEN_DESCRIPTIONS: dict[str, str] = {
    "surface": "Primary application background",
    "surface_alt": "Secondary panel background",
    "surface_raised": "Raised card and dialog background",
    "text": "Primary text color",
    "text_muted": "Secondary text color",
    "text_subtle": "Tertiary text and placeholder color",
    "accent": "Primary interactive color",
    "accent_hover": "Interactive color on hover",
    "on_accent": "Text placed on accent surfaces",
    "border": "Subtle divider color",
    "border_strong": "Emphasized outline color",
    "focus": "Keyboard focus indicator color",
    "success": "Positive status color",
    "warning": "Caution status color",
    "danger": "Destructive status color",
    "info": "Informational status color",
}

GRAPHITE_TOKENS: dict[str, str] = {
    "surface": "#10131a",
    "surface_alt": "#171b25",
    "surface_raised": "#1d2230",
    "text": "#f2f5fb",
    "text_muted": "#b8c0d0",
    "text_subtle": "#8d97aa",
    "accent": "#8ab4ff",
    "accent_hover": "#a9c7ff",
    "on_accent": "#081020",
    "border": "#2e3545",
    "border_strong": "#58627a",
    "focus": "#ffcc66",
    "success": "#7ee2a8",
    "warning": "#ffcf70",
    "danger": "#ff8f8f",
    "info": "#91c9ff",
}

PAPER_TOKENS: dict[str, str] = {
    "surface": "#fbfbf8",
    "surface_alt": "#f1f1ec",
    "surface_raised": "#ffffff",
    "text": "#1b1f27",
    "text_muted": "#4d5666",
    "text_subtle": "#6c7585",
    "accent": "#2457b8",
    "accent_hover": "#17429b",
    "on_accent": "#ffffff",
    "border": "#d3d6dd",
    "border_strong": "#8b94a6",
    "focus": "#a03a00",
    "success": "#146c43",
    "warning": "#8a5a00",
    "danger": "#b42318",
    "info": "#175cd3",
}

HIGH_CONTRAST_DARK_TOKENS: dict[str, str] = {
    "surface": "#000000",
    "surface_alt": "#0a0a0a",
    "surface_raised": "#121212",
    "text": "#ffffff",
    "text_muted": "#f0f0f0",
    "text_subtle": "#dddddd",
    "accent": "#ffff00",
    "accent_hover": "#ffff66",
    "on_accent": "#000000",
    "border": "#ffffff",
    "border_strong": "#ffffff",
    "focus": "#00ff00",
    "success": "#00ff88",
    "warning": "#ffcc00",
    "danger": "#ff4444",
    "info": "#66ccff",
}

HIGH_CONTRAST_LIGHT_TOKENS: dict[str, str] = {
    "surface": "#ffffff",
    "surface_alt": "#f4f4f4",
    "surface_raised": "#ffffff",
    "text": "#000000",
    "text_muted": "#111111",
    "text_subtle": "#222222",
    "accent": "#0000cc",
    "accent_hover": "#000088",
    "on_accent": "#ffffff",
    "border": "#000000",
    "border_strong": "#000000",
    "focus": "#cc0000",
    "success": "#006400",
    "warning": "#8b5000",
    "danger": "#a00000",
    "info": "#0033a0",
}

MIDNIGHT_TOKENS: dict[str, str] = {
    **GRAPHITE_TOKENS,
    "surface": "#0b1026",
    "surface_alt": "#111834",
    "surface_raised": "#182142",
    "accent": "#b39aff",
    "accent_hover": "#cdbcff",
    "on_accent": "#100a24",
    "border": "#2c3668",
    "focus": "#ffd580",
}

FOREST_TOKENS: dict[str, str] = {
    **PAPER_TOKENS,
    "surface": "#f5f8f2",
    "surface_alt": "#e8efe2",
    "surface_raised": "#ffffff",
    "accent": "#256b3a",
    "accent_hover": "#1b522c",
    "focus": "#8a5a00",
    "success": "#146c43",
}

BUILTIN_THEMES: dict[str, ThemeDefinition] = {
    "graphite": ThemeDefinition(
        name="graphite",
        label="Graphite",
        mode="dark",
        tokens=dict(GRAPHITE_TOKENS),
        description="Balanced dark theme for long research sessions.",
        accent_hue=215,
    ),
    "paper": ThemeDefinition(
        name="paper",
        label="Paper",
        mode="light",
        tokens=dict(PAPER_TOKENS),
        description="Warm light theme with neutral surfaces.",
        accent_hue=220,
    ),
    "high-contrast-dark": ThemeDefinition(
        name="high-contrast-dark",
        label="High Contrast Dark",
        mode="dark",
        tokens=dict(HIGH_CONTRAST_DARK_TOKENS),
        description="Maximum contrast dark theme for low vision.",
        accent_hue=60,
    ),
    "high-contrast-light": ThemeDefinition(
        name="high-contrast-light",
        label="High Contrast Light",
        mode="light",
        tokens=dict(HIGH_CONTRAST_LIGHT_TOKENS),
        description="Maximum contrast light theme for bright rooms.",
        accent_hue=240,
    ),
    "midnight": ThemeDefinition(
        name="midnight",
        label="Midnight",
        mode="dark",
        tokens=dict(MIDNIGHT_TOKENS),
        description="Deep blue dark theme with violet accents.",
        extends="graphite",
        accent_hue=265,
    ),
    "forest": ThemeDefinition(
        name="forest",
        label="Forest",
        mode="light",
        tokens=dict(FOREST_TOKENS),
        description="Soft green light theme.",
        extends="paper",
        accent_hue=140,
    ),
}

TOKEN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CSS_NAME_RE = re.compile(r"[^a-z0-9]+")


def token_to_css(name: str) -> str:
    """Convert a token name to a CSS custom property name."""
    normalized = CSS_NAME_RE.sub("-", name.strip().lower()).strip("-")
    return f"--a11y-{normalized}"


def css_to_token(name: str) -> str:
    """Convert a CSS custom property name back to a token name."""
    stripped = name.strip().lstrip("-")
    if stripped.startswith("a11y-"):
        stripped = stripped[5:]
    return stripped.replace("-", "_")


def normalize_theme_name(name: str) -> str:
    """Normalize a theme name."""
    return CSS_NAME_RE.sub("-", name.strip().lower()).strip("-")


def validate_token_name(name: str) -> str:
    """Validate and normalize a theme token name."""
    normalized = name.strip().lower()
    if not TOKEN_NAME_RE.match(normalized):
        raise ValueError(f"Invalid theme token name: {name}")
    return normalized


def missing_tokens(theme: ThemeDefinition) -> tuple[str, ...]:
    """Return required tokens that a theme does not define."""
    return tuple(sorted(REQUIRED_TOKENS - set(theme.tokens)))


def create_theme(
    name: str,
    label: str,
    *,
    mode: str = "dark",
    tokens: Mapping[str, str] | None = None,
    base: str = "graphite",
    description: str = "",
    accent_hue: int = 210,
) -> ThemeDefinition:
    """Create a theme with token inheritance from a built-in base."""
    normalized_name = normalize_theme_name(name)
    if not normalized_name:
        raise ValueError("Theme name cannot be empty")
    parent = BUILTIN_THEMES.get(base)
    merged = dict(parent.tokens) if parent else {}
    for key, value in (tokens or {}).items():
        merged[validate_token_name(key)] = str(value)
    return ThemeDefinition(
        name=normalized_name,
        label=label or normalized_name.replace("-", " ").title(),
        mode=mode,
        tokens=merged,
        description=description,
        extends=base if parent else "",
        accent_hue=accent_hue,
    )


def resolve_theme(
    theme: ThemeDefinition | str,
    *,
    registry: Mapping[str, ThemeDefinition] | None = None,
    overrides: Mapping[str, str] | None = None,
) -> ThemeDefinition:
    """Resolve a theme by name and apply token overrides."""
    if isinstance(theme, ThemeDefinition):
        resolved = theme
    else:
        name = normalize_theme_name(theme)
        sources = registry or BUILTIN_THEMES
        found = sources.get(name)
        if found is None:
            found = BUILTIN_THEMES.get(name)
        if found is None:
            raise ValueError(f"Unknown theme: {theme}")
        resolved = found
    if not overrides:
        return resolved
    tokens = dict(resolved.tokens)
    for key, value in overrides.items():
        tokens[validate_token_name(key)] = str(value)
    return ThemeDefinition(
        name=resolved.name,
        label=resolved.label,
        mode=resolved.mode,
        tokens=tokens,
        description=resolved.description,
        extends=resolved.extends,
        accent_hue=resolved.accent_hue,
    )


def theme_css(theme: ThemeDefinition, *, selector: str = ":root", indent: str = "  ") -> str:
    """Emit CSS custom properties for a theme."""
    lines = [f"{selector} {{"]
    for name in sorted(theme.tokens):
        lines.append(f"{indent}{token_to_css(name)}: {theme.tokens[name]};")
    lines.append("}")
    return "\n".join(lines)


def theme_from_payload(payload: Mapping[str, Any]) -> ThemeDefinition:
    """Build a theme definition from API input."""
    name = str(payload.get("name", "custom"))
    tokens = {
        validate_token_name(str(key)): str(value)
        for key, value in (payload.get("tokens") or {}).items()
    }
    base = str(payload.get("extends") or "graphite")
    try:
        hue = int(payload.get("accent_hue", 210))
    except (TypeError, ValueError):
        hue = 210
    return create_theme(
        name,
        str(payload.get("label") or name),
        mode=str(payload.get("mode") or "dark"),
        tokens=tokens,
        base=base,
        description=str(payload.get("description") or ""),
        accent_hue=hue,
    )


def theme_diff(first: ThemeDefinition, second: ThemeDefinition) -> dict[str, Any]:
    """Compare two themes by token value."""
    names = sorted(set(first.tokens) | set(second.tokens))
    added: dict[str, str] = {}
    removed: dict[str, str] = {}
    changed: dict[str, dict[str, str]] = {}
    for name in names:
        left = first.tokens.get(name)
        right = second.tokens.get(name)
        if left is None and right is not None:
            added[name] = right
        elif right is None and left is not None:
            removed[name] = left
        elif left != right and left is not None and right is not None:
            changed[name] = {"from": left, "to": right}
    return {
        "first": first.name,
        "second": second.name,
        "added": added,
        "removed": removed,
        "changed": changed,
        "count": len(added) + len(removed) + len(changed),
    }


def token_catalog(theme: ThemeDefinition | None = None) -> tuple[ThemeToken, ...]:
    """Return metadata for all known theme tokens."""
    source = theme.tokens if theme else REQUIRED_TOKENS
    tokens: list[ThemeToken] = []
    for name in sorted(source):
        category = "surface"
        if name.startswith("text"):
            category = "text"
        elif "accent" in name:
            category = "accent"
        elif "border" in name or name == "focus":
            category = "border"
        elif name in {"success", "warning", "danger", "info"}:
            category = "status"
        tokens.append(
            ThemeToken(
                name=name,
                value=source[name] if isinstance(source, dict) else "",
                category=category,
                description=TOKEN_DESCRIPTIONS.get(name, ""),
            )
        )
    return tuple(tokens)


def theme_options(registry: Mapping[str, ThemeDefinition] | None = None) -> list[dict[str, Any]]:
    """Return theme options for a picker UI."""
    source = registry or BUILTIN_THEMES
    return [
        {
            "value": theme.name,
            "label": theme.label,
            "mode": theme.mode,
            "description": theme.description,
            "accent": theme.tokens.get("accent", ""),
        }
        for _, theme in sorted(source.items())
    ]


class ThemeRegistry:
    """A mutable registry of theme definitions."""

    def __init__(self, themes: Mapping[str, ThemeDefinition] | None = None) -> None:
        self._themes: dict[str, ThemeDefinition] = dict(BUILTIN_THEMES.items())
        for name, definition in (themes or {}).items():
            self.register(
                definition
                if definition.name == name
                else ThemeDefinition(
                    name, definition.label, definition.mode, dict(definition.tokens)
                )
            )

    def __contains__(self, name: str) -> bool:
        return normalize_theme_name(name) in self._themes

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._themes))

    def get(self, name: str) -> ThemeDefinition | None:
        return self._themes.get(normalize_theme_name(name))

    def require(self, name: str) -> ThemeDefinition:
        theme = self.get(name)
        if theme is None:
            raise ValueError(f"Unknown theme: {name}")
        return theme

    def register(self, theme: ThemeDefinition) -> ThemeDefinition:
        """Register or replace a theme."""
        name = normalize_theme_name(theme.name)
        stored = ThemeDefinition(
            name=name,
            label=theme.label,
            mode=theme.mode,
            tokens=dict(theme.tokens),
            description=theme.description,
            extends=theme.extends,
            accent_hue=theme.accent_hue,
        )
        self._themes[name] = stored
        return stored

    def remove(self, name: str) -> ThemeDefinition | None:
        return self._themes.pop(normalize_theme_name(name), None)

    def resolve(self, name: str, *, overrides: Mapping[str, str] | None = None) -> ThemeDefinition:
        return resolve_theme(self.require(name), overrides=overrides)

    def validate(self) -> dict[str, Any]:
        """Validate all registered themes for required tokens."""
        problems: dict[str, list[str]] = {}
        for name, theme in sorted(self._themes.items()):
            missing = missing_tokens(theme)
            if missing:
                problems[name] = list(missing)
        return {
            "themes": len(self._themes),
            "invalid": problems,
            "valid": not problems,
        }

    def options(self) -> list[dict[str, Any]]:
        return theme_options(self._themes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "themes": {name: self._themes[name].as_dict() for name in self.names},
        }


def generate_accent_palette(hue: int, *, mode: str = "dark") -> dict[str, str]:
    """Generate a simple accent palette from a hue value."""
    normalized_hue = hue % 360
    lightness = 68 if mode == "dark" else 40
    hover_lightness = 80 if mode == "dark" else 30
    return {
        "accent": f"hsl({normalized_hue} 85% {lightness}%)",
        "accent_hover": f"hsl({normalized_hue} 85% {hover_lightness}%)",
        "on_accent": "#000000" if mode == "dark" else "#ffffff",
        "focus": f"hsl({(normalized_hue + 180) % 360} 95% 65%)",
    }


def theme_summary(theme: ThemeDefinition) -> dict[str, Any]:
    """Return a compact summary for a theme."""
    return {
        "name": theme.name,
        "label": theme.label,
        "mode": theme.mode,
        "token_count": len(theme.tokens),
        "missing": list(missing_tokens(theme)),
        "extends": theme.extends,
        "accent": theme.token("accent"),
    }


def themes_css(registry: Mapping[str, ThemeDefinition] | None = None) -> str:
    """Emit CSS blocks for every theme."""
    source = registry or BUILTIN_THEMES
    blocks = [
        theme_css(theme, selector=f'[data-a11y-theme="{name}"]')
        for name, theme in sorted(source.items())
    ]
    return "\n\n".join(blocks)


def token_values(theme: ThemeDefinition, names: Sequence[str]) -> dict[str, str]:
    """Return selected token values from a theme."""
    return {name: theme.tokens.get(name, "") for name in names}
