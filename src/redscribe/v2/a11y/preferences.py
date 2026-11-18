"""Preference models, validation, migration, and persistence helpers."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from redscribe.v2.a11y.i18n.locales import (
    direction_for,
    fallback_chain,
    is_valid_locale,
    lookup_locale,
    normalize_locale,
)
from redscribe.v2.a11y.models import Direction, PreferenceSnapshot
from redscribe.v2.a11y.shortcuts import ShortcutRegistry, normalize_binding
from redscribe.v2.a11y.themes import normalize_theme_name

PREFERENCE_VERSION = 2
FONT_SCALE_MIN = 0.75
FONT_SCALE_MAX = 1.75
LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


@dataclass(frozen=True, slots=True)
class PreferenceIssue:
    """A validation finding for preference input."""

    field: str
    message: str
    code: str = "invalid_value"

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "message": self.message, "code": self.code}


@dataclass(frozen=True, slots=True)
class PreferenceRecord:
    """A stored snapshot with version metadata."""

    snapshot: PreferenceSnapshot
    version: int = PREFERENCE_VERSION
    profile: str = "default"
    source: str = "local"
    signature: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile,
            "source": self.source,
            "signature": self.signature,
            "preferences": self.snapshot.as_dict(),
        }


def default_preferences(
    *,
    locale: str = "en",
    theme: str = "graphite",
) -> PreferenceSnapshot:
    """Return a validated default preference snapshot."""
    return PreferenceSnapshot(
        locale=normalize_locale(locale),
        theme=normalize_theme_name(theme),
        direction=Direction.AUTO,
        font_scale=1.0,
        reduce_motion=False,
        high_contrast=False,
        screen_reader_hints=True,
        focus_ring_boost=False,
        shortcuts={},
        updated_at="",
        revision=1,
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def validate_preferences(
    payload: Mapping[str, Any],
) -> tuple[PreferenceSnapshot, tuple[PreferenceIssue, ...]]:
    """Validate and normalize a preference payload."""
    issues: list[PreferenceIssue] = []
    defaults = default_preferences()

    raw_locale = payload.get("locale", defaults.locale)
    locale = normalize_locale(str(raw_locale)) if isinstance(raw_locale, str) else str(raw_locale)
    if not isinstance(raw_locale, str) or not LOCALE_RE.match(locale):
        issues.append(PreferenceIssue("locale", "Locale must be a valid language tag"))
        locale = defaults.locale

    raw_theme = payload.get("theme", defaults.theme)
    theme = normalize_theme_name(str(raw_theme))
    if not theme:
        issues.append(PreferenceIssue("theme", "Theme must not be empty"))
        theme = defaults.theme

    raw_direction = payload.get("direction", defaults.direction.value)
    if isinstance(raw_direction, Direction):
        direction = raw_direction
    else:
        text = str(raw_direction or Direction.AUTO.value).lower()
        try:
            direction = Direction(text)
        except ValueError:
            issues.append(PreferenceIssue("direction", "Direction must be ltr, rtl, or auto"))
            direction = defaults.direction

    scale = _number(payload.get("font_scale", defaults.font_scale))
    if scale is None:
        issues.append(PreferenceIssue("font_scale", "Font scale must be numeric"))
        scale = defaults.font_scale
    elif not FONT_SCALE_MIN <= scale <= FONT_SCALE_MAX:
        issues.append(
            PreferenceIssue(
                "font_scale", "Font scale must be between 0.75 and 1.75", "out_of_range"
            )
        )
        scale = min(FONT_SCALE_MAX, max(FONT_SCALE_MIN, scale))

    boolean_fields = (
        "reduce_motion",
        "high_contrast",
        "screen_reader_hints",
        "focus_ring_boost",
    )
    booleans: dict[str, bool] = {}
    for name in boolean_fields:
        parsed = _bool(payload.get(name, getattr(defaults, name)))
        if parsed is None:
            issues.append(PreferenceIssue(name, f"{name} must be a boolean", "invalid_type"))
            parsed = bool(getattr(defaults, name))
        booleans[name] = parsed

    raw_shortcuts = payload.get("shortcuts") or {}
    shortcuts: dict[str, list[str]] = {}
    if not isinstance(raw_shortcuts, Mapping):
        issues.append(PreferenceIssue("shortcuts", "Shortcuts must be an object", "invalid_type"))
    else:
        for action, keys in raw_shortcuts.items():
            if not isinstance(keys, Sequence) or isinstance(keys, str):
                issues.append(
                    PreferenceIssue(
                        f"shortcuts.{action}", "Shortcut keys must be an array", "invalid_type"
                    )
                )
                continue
            normalized = normalize_binding(keys)
            if not normalized:
                issues.append(
                    PreferenceIssue(f"shortcuts.{action}", "Shortcut keys must not be empty")
                )
                continue
            shortcuts[str(action)] = list(normalized)

    revision = payload.get("revision", 1)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        issues.append(PreferenceIssue("revision", "Revision must be a positive integer"))
        revision = 1

    snapshot = PreferenceSnapshot(
        locale=locale,
        theme=theme,
        direction=direction,
        font_scale=round(scale, 3),
        reduce_motion=booleans["reduce_motion"],
        high_contrast=booleans["high_contrast"],
        screen_reader_hints=booleans["screen_reader_hints"],
        focus_ring_boost=booleans["focus_ring_boost"],
        shortcuts=shortcuts,
        updated_at=str(payload.get("updated_at") or ""),
        revision=revision,
    )
    return snapshot, tuple(issues)


def merge_preferences(
    current: PreferenceSnapshot,
    patch: Mapping[str, Any],
    *,
    now: str = "",
) -> PreferenceSnapshot:
    """Apply a partial preference patch to a snapshot."""
    merged = current.as_dict()
    for key, value in patch.items():
        if key in merged:
            merged[key] = value
    snapshot, _ = validate_preferences(merged)
    return PreferenceSnapshot(
        locale=snapshot.locale,
        theme=snapshot.theme,
        direction=snapshot.direction,
        font_scale=snapshot.font_scale,
        reduce_motion=snapshot.reduce_motion,
        high_contrast=snapshot.high_contrast,
        screen_reader_hints=snapshot.screen_reader_hints,
        focus_ring_boost=snapshot.focus_ring_boost,
        shortcuts=snapshot.shortcuts,
        updated_at=now or current.updated_at,
        revision=current.revision + 1,
    )


def effective_direction(snapshot: PreferenceSnapshot) -> Direction:
    """Resolve the effective text direction from locale and override."""
    if snapshot.direction == Direction.AUTO:
        return direction_for(snapshot.locale)
    return snapshot.direction


def preference_fallbacks(snapshot: PreferenceSnapshot) -> tuple[str, ...]:
    """Return locale fallbacks for a preference snapshot."""
    return fallback_chain(snapshot.locale)


def is_preference_supported(snapshot: PreferenceSnapshot) -> bool:
    """Return whether the snapshot references a known locale."""
    return lookup_locale(snapshot.locale) is not None


def snapshot_signature(snapshot: PreferenceSnapshot) -> str:
    """Return a stable signature for a preference snapshot."""
    payload = snapshot.as_dict()
    payload.pop("updated_at", None)
    payload.pop("revision", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def migrate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate legacy preference payloads to the current schema."""
    migrated = dict(payload)
    version = migrated.get("version", 1)
    if version == 1:
        legacy_direction = migrated.pop("rtl", None)
        if isinstance(legacy_direction, bool) and legacy_direction:
            migrated["direction"] = Direction.RTL.value
        migrated["version"] = 2
    if "fontScale" in migrated:
        migrated["font_scale"] = migrated.pop("fontScale")
    if "reduceMotion" in migrated:
        migrated["reduce_motion"] = migrated.pop("reduceMotion")
    if "highContrast" in migrated:
        migrated["high_contrast"] = migrated.pop("highContrast")
    if "screenReaderHints" in migrated:
        migrated["screen_reader_hints"] = migrated.pop("screenReaderHints")
    migrated.setdefault("version", PREFERENCE_VERSION)
    return migrated


def export_preferences(record: PreferenceRecord) -> dict[str, Any]:
    """Export a preference record as portable JSON data."""
    payload = record.as_dict()
    payload["schema"] = "redscribe.a11y.preferences"
    return payload


def import_preferences(payload: Mapping[str, Any]) -> PreferenceRecord:
    """Import a preference record from portable JSON data."""
    migrated = migrate_payload(payload)
    raw_nested = migrated.get("preferences")
    nested: Mapping[str, Any] = raw_nested if isinstance(raw_nested, Mapping) else migrated
    snapshot, issues = validate_preferences(nested)
    if any(issue.code == "invalid_type" for issue in issues):
        raise ValueError("Preference payload contains invalid fields")
    version = migrated.get("version", PREFERENCE_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        version = PREFERENCE_VERSION
    return PreferenceRecord(
        snapshot=snapshot,
        version=version,
        profile=str(migrated.get("profile") or "default"),
        source=str(migrated.get("source") or "import"),
        signature=snapshot_signature(snapshot),
    )


class PreferenceStore(Protocol):
    """Storage contract for preference records."""

    def load(self, profile: str = "default") -> PreferenceRecord | None: ...

    def save(self, record: PreferenceRecord) -> None: ...

    def profiles(self) -> tuple[str, ...]: ...


class MemoryPreferenceStore:
    """In-memory preference storage for tests and ephemeral sessions."""

    def __init__(self) -> None:
        self._records: dict[str, PreferenceRecord] = {}

    def load(self, profile: str = "default") -> PreferenceRecord | None:
        return self._records.get(profile)

    def save(self, record: PreferenceRecord) -> None:
        self._records[record.profile] = record

    def profiles(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def clear(self) -> None:
        self._records.clear()


class JsonPreferenceStore:
    """File-backed preference storage with atomic writes."""

    def __init__(self, path: str | Path, *, profiles: Sequence[str] = ("default",)) -> None:
        self._path = Path(path)
        self._allowed = tuple(profiles)

    @property
    def path(self) -> Path:
        return self._path

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, Mapping):
            return {}
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, Mapping):
                result[str(key)] = dict(value)
        return result

    def _write(self, payload: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_name, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise

    def load(self, profile: str = "default") -> PreferenceRecord | None:
        payload = self._read().get(profile)
        if payload is None:
            return None
        try:
            return import_preferences({**payload, "profile": profile, "source": "file"})
        except ValueError:
            return None

    def save(self, record: PreferenceRecord) -> None:
        payload = self._read()
        payload[record.profile] = export_preferences(record)
        self._write(payload)

    def profiles(self) -> tuple[str, ...]:
        return tuple(sorted(self._read()))


@dataclass(slots=True)
class PreferenceService:
    """Application service for preference reads, writes, and validation."""

    store: PreferenceStore
    registry: ShortcutRegistry = field(default_factory=ShortcutRegistry)

    def current(self, profile: str = "default") -> PreferenceSnapshot:
        """Return stored preferences or defaults."""
        record = self.store.load(profile)
        return record.snapshot if record else default_preferences()

    def record(self, profile: str = "default") -> PreferenceRecord:
        """Return the full stored record or a default record."""
        found = self.store.load(profile)
        if found is not None:
            return found
        snapshot = default_preferences()
        return PreferenceRecord(snapshot=snapshot, signature=snapshot_signature(snapshot))

    def validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a preference payload without saving it."""
        snapshot, issues = validate_preferences(migrate_payload(payload))
        return {
            "valid": not issues,
            "issues": [issue.as_dict() for issue in issues],
            "preferences": snapshot.as_dict(),
        }

    def update(
        self,
        patch: Mapping[str, Any],
        *,
        profile: str = "default",
        now: str = "",
    ) -> PreferenceRecord:
        """Merge a patch into stored preferences and persist it."""
        current = self.current(profile)
        migrated = migrate_payload(patch)
        merged = merge_preferences(current, migrated, now=now)
        snapshot, issues = validate_preferences(merged.as_dict())
        if issues:
            raise ValueError("; ".join(issue.message for issue in issues))
        record = PreferenceRecord(
            snapshot=snapshot,
            version=PREFERENCE_VERSION,
            profile=profile,
            signature=snapshot_signature(snapshot),
        )
        self.store.save(record)
        return record

    def replace(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
    ) -> PreferenceRecord:
        """Replace stored preferences with a complete payload."""
        imported = import_preferences({**payload, "profile": profile, "source": "request"})
        self.store.save(imported)
        return imported

    def reset(self, *, profile: str = "default") -> PreferenceRecord:
        """Reset a profile to defaults."""
        snapshot = default_preferences()
        record = PreferenceRecord(
            snapshot=snapshot, profile=profile, signature=snapshot_signature(snapshot)
        )
        self.store.save(record)
        return record

    def shortcut_bindings(self, profile: str = "default") -> dict[str, list[str]]:
        """Return effective shortcut bindings for a profile."""
        result = self.registry.to_payload()
        result.update(self.current(profile).shortcuts)
        return result

    def effective(self, profile: str = "default") -> dict[str, Any]:
        """Return effective settings including derived values."""
        snapshot = self.current(profile)
        return {
            "preferences": snapshot.as_dict(),
            "direction": effective_direction(snapshot).value,
            "fallbacks": list(preference_fallbacks(snapshot)),
            "shortcuts": self.shortcut_bindings(profile),
            "supported_locale": is_preference_supported(snapshot),
            "signature": snapshot_signature(snapshot),
        }

    def profiles(self) -> tuple[str, ...]:
        return self.store.profiles()

    def export(self, profile: str = "default") -> dict[str, Any]:
        return export_preferences(self.record(profile))

    def import_record(
        self, payload: Mapping[str, Any], *, profile: str = "default"
    ) -> PreferenceRecord:
        record = import_preferences({**payload, "profile": profile})
        self.store.save(record)
        return record


def preference_defaults_payload() -> dict[str, Any]:
    """Return default preferences as an API payload."""
    snapshot = default_preferences()
    return snapshot.as_dict()


def preference_schema() -> dict[str, Any]:
    """Return a machine-readable description of preference fields."""
    return {
        "version": PREFERENCE_VERSION,
        "fields": {
            "locale": {"type": "string", "default": "en"},
            "theme": {"type": "string", "default": "graphite"},
            "direction": {
                "type": "string",
                "enum": [item.value for item in Direction],
                "default": "auto",
            },
            "font_scale": {
                "type": "number",
                "min": FONT_SCALE_MIN,
                "max": FONT_SCALE_MAX,
                "default": 1.0,
            },
            "reduce_motion": {"type": "boolean", "default": False},
            "high_contrast": {"type": "boolean", "default": False},
            "screen_reader_hints": {"type": "boolean", "default": True},
            "focus_ring_boost": {"type": "boolean", "default": False},
            "shortcuts": {"type": "object", "default": {}},
        },
    }


def merge_shortcut_overrides(
    registry: ShortcutRegistry,
    overrides: Mapping[str, Sequence[str]],
) -> ShortcutRegistry:
    """Apply stored shortcut overrides to a registry copy."""
    result = ShortcutRegistry(registry.values())
    for action, keys in overrides.items():
        if action in result:
            result.update_keys(action, keys)
    return result


def locale_preference_options() -> list[dict[str, Any]]:
    """Return locale options filtered to syntactically valid tags."""
    from redscribe.v2.a11y.i18n.locales import locale_options

    return [option for option in locale_options() if is_valid_locale(str(option["value"]))]


def preference_diff(first: PreferenceSnapshot, second: PreferenceSnapshot) -> dict[str, Any]:
    """Compare two preference snapshots."""
    left = first.as_dict()
    right = second.as_dict()
    changed = {
        key: {"from": left[key], "to": right[key]}
        for key in sorted(left)
        if left[key] != right[key] and key not in {"updated_at", "revision"}
    }
    return {"changed": changed, "count": len(changed)}
