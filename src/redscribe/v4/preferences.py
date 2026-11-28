"""Preference model for themes, density, motion, and locale.

Preferences are plain data with strict validation and a deterministic merge
operation, so a vault can persist them without any runtime dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

SUPPORTED_LOCALES = ("en", "fr", "es", "de", "ar", "ja", "zh")
SUPPORTED_THEMES = ("light", "graphite", "system")
SUPPORTED_DENSITIES = ("compact", "default", "comfortable")
SUPPORTED_MOTION = ("full", "subtle", "off")


@dataclass(frozen=True, slots=True)
class Preferences:
    """User-facing display preferences."""

    theme: str = "light"
    density: str = "default"
    motion: str = "full"
    locale: str = "en"
    direction: str = "ltr"
    reduce_transparency: bool = False
    high_contrast: bool = False
    font_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.theme not in SUPPORTED_THEMES:
            raise ValueError(f"unsupported theme: {self.theme}")
        if self.density not in SUPPORTED_DENSITIES:
            raise ValueError(f"unsupported density: {self.density}")
        if self.motion not in SUPPORTED_MOTION:
            raise ValueError(f"unsupported motion: {self.motion}")
        if self.locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale: {self.locale}")
        if self.direction not in {"ltr", "rtl"}:
            raise ValueError(f"unsupported direction: {self.direction}")
        if not 0.75 <= self.font_scale <= 2.0:
            raise ValueError(f"font_scale out of range: {self.font_scale}")
        if self.locale == "ar" and self.direction != "rtl":
            raise ValueError("Arabic locale requires rtl direction")

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "density": self.density,
            "motion": self.motion,
            "locale": self.locale,
            "direction": self.direction,
            "reduce_transparency": self.reduce_transparency,
            "high_contrast": self.high_contrast,
            "font_scale": self.font_scale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Preferences:
        return cls(
            theme=str(data.get("theme", "light")),
            density=str(data.get("density", "default")),
            motion=str(data.get("motion", "full")),
            locale=str(data.get("locale", "en")),
            direction=str(data.get("direction", "ltr")),
            reduce_transparency=bool(data.get("reduce_transparency", False)),
            high_contrast=bool(data.get("high_contrast", False)),
            font_scale=float(data.get("font_scale", 1.0)),
        )

    def merged(self, overrides: Mapping[str, Any]) -> Preferences:
        """Return a new Preferences with validated overrides applied."""
        known = {
            "theme",
            "density",
            "motion",
            "locale",
            "direction",
            "reduce_transparency",
            "high_contrast",
            "font_scale",
        }
        clean = {key: value for key, value in overrides.items() if key in known}
        return replace(self, **clean)

    @property
    def css_dataset(self) -> dict[str, str]:
        """Attributes to apply to the document root."""
        return {
            "v4Theme": self.theme,
            "v4Density": self.density,
            "v4Motion": self.motion,
            "dir": self.direction,
        }


class PreferenceStore:
    """An in-memory store with a revision counter and change listeners."""

    def __init__(self, initial: Preferences | None = None) -> None:
        self._current = initial or Preferences()
        self._revision = 0
        self._listeners: list[Any] = []

    @property
    def current(self) -> Preferences:
        return self._current

    @property
    def revision(self) -> int:
        return self._revision

    def update(self, overrides: Mapping[str, Any]) -> Preferences:
        updated = self._current.merged(overrides)
        if updated != self._current:
            self._current = updated
            self._revision += 1
            for listener in list(self._listeners):
                listener(updated, self._revision)
        return self._current

    def listen(self, listener: Any) -> None:
        self._listeners.append(listener)

    def reset(self) -> None:
        self._current = Preferences()
        self._revision += 1
