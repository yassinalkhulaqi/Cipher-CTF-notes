"""Preference synchronization and one unified theme/motion control.

V2 owns persistent preference validation. This layer adds cross-feature sync
with versioned checksums, explicit conflict strategies, and an appearance
record that drives theme, motion, density, and direction from one source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from json import dumps
from typing import Any

from redscribe.v2.a11y.models import Direction, FocusMode, PreferenceSnapshot, Shortcut
from redscribe.v2.a11y.preferences import (
    default_preferences,
    snapshot_signature,
    validate_preferences,
)
from redscribe.v2.a11y.shortcuts import normalize_binding
from redscribe.v3.a11y_refinement.models import (
    MotionMode,
    PreferenceSyncRecord,
    SyncReport,
    SyncStrategy,
)

SYNC_FIELDS: tuple[str, ...] = (
    "locale",
    "theme",
    "direction",
    "font_scale",
    "reduce_motion",
    "high_contrast",
    "screen_reader_hints",
    "focus_ring_boost",
    "shortcuts",
)

MOTION_MARKER = "v3.motion_mode"

MOTION_DURATIONS: dict[MotionMode, dict[str, str]] = {
    MotionMode.FULL: {"fast": "120ms", "normal": "220ms", "slow": "360ms"},
    MotionMode.REDUCED: {"fast": "1ms", "normal": "1ms", "slow": "1ms"},
    MotionMode.OFF: {"fast": "0ms", "normal": "0ms", "slow": "0ms"},
}


@dataclass(frozen=True, slots=True)
class UnifiedAppearance:
    """One control surface for theme, motion, and layout preferences."""

    theme: str = "graphite"
    motion: MotionMode = MotionMode.FULL
    density: str = "comfortable"
    direction: Direction = Direction.AUTO
    font_scale: float = 1.0
    high_contrast: bool = False
    focus_ring_boost: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe appearance record."""
        return {
            "theme": self.theme,
            "motion": self.motion.value,
            "density": self.density,
            "direction": self.direction.value,
            "font_scale": self.font_scale,
            "high_contrast": self.high_contrast,
            "focus_ring_boost": self.focus_ring_boost,
        }


DEFAULT_APPEARANCE = UnifiedAppearance()


def checksum(snapshot: PreferenceSnapshot) -> str:
    """Return a stable checksum for a snapshot's durable fields."""
    payload = {field_name: getattr(snapshot, field_name) for field_name in SYNC_FIELDS}
    text = dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(text.encode("utf-8")).hexdigest()[:16]


def record_from_snapshot(
    snapshot: PreferenceSnapshot,
    *,
    profile: str = "default",
    source: str = "local",
    tags: Sequence[str] = (),
) -> PreferenceSyncRecord:
    """Wrap a snapshot in a versioned sync record."""
    return PreferenceSyncRecord(
        profile=profile,
        snapshot=snapshot,
        revision=max(1, snapshot.revision),
        source=source,
        checksum=checksum(snapshot),
        tags=tuple(tags),
    )


def snapshot_from_payload(payload: Mapping[str, Any]) -> PreferenceSnapshot:
    """Validate and import a snapshot from an API payload."""
    migrated = dict(payload)
    snapshot, issues = validate_preferences(migrated)
    if issues:
        raise ValueError("; ".join(issue.message for issue in issues))
    return snapshot


def snapshot_from_record(record: PreferenceSyncRecord) -> PreferenceSnapshot:
    """Return the snapshot inside a sync record."""
    return record.snapshot


def appearance_from_snapshot(snapshot: PreferenceSnapshot) -> UnifiedAppearance:
    """Derive the unified appearance control from stored preferences."""
    try:
        if list(snapshot.shortcuts.get(MOTION_MARKER, ())) == ["off"]:
            motion = MotionMode.OFF
        else:
            motion = MotionMode.REDUCED if snapshot.reduce_motion else MotionMode.FULL
        return UnifiedAppearance(
            theme=snapshot.theme,
            motion=motion,
            density="compact" if snapshot.focus_ring_boost else "comfortable",
            direction=snapshot.direction,
            font_scale=snapshot.font_scale,
            high_contrast=snapshot.high_contrast,
            focus_ring_boost=snapshot.focus_ring_boost,
        )
    except (TypeError, ValueError):
        return DEFAULT_APPEARANCE


def apply_appearance(
    snapshot: PreferenceSnapshot, appearance: UnifiedAppearance
) -> PreferenceSnapshot:
    """Apply one appearance record to a preference snapshot."""
    reduced = appearance.motion in {MotionMode.REDUCED, MotionMode.OFF}
    shortcuts = dict(snapshot.shortcuts)
    if appearance.motion == MotionMode.OFF:
        shortcuts[MOTION_MARKER] = ["off"]
    else:
        shortcuts.pop(MOTION_MARKER, None)
    return replace(
        snapshot,
        theme=appearance.theme,
        direction=appearance.direction,
        font_scale=appearance.font_scale,
        reduce_motion=reduced,
        high_contrast=appearance.high_contrast,
        focus_ring_boost=appearance.focus_ring_boost,
        shortcuts=shortcuts,
        revision=snapshot.revision + 1,
    )


def appearance_css(appearance: UnifiedAppearance) -> dict[str, str]:
    """Render the unified appearance as CSS custom properties."""
    durations = MOTION_DURATIONS[appearance.motion]
    return {
        "--v3-theme": appearance.theme,
        "--v3-density": appearance.density,
        "--v3-direction": appearance.direction.value,
        "--v3-font-scale": f"{appearance.font_scale:.2f}",
        "--v3-motion-fast": durations["fast"],
        "--v3-motion-normal": durations["normal"],
        "--v3-motion-slow": durations["slow"],
        "--v3-focus-boost": "1" if appearance.focus_ring_boost else "0",
        "--v3-contrast": "high" if appearance.high_contrast else "normal",
    }


def diff_records(
    local: PreferenceSyncRecord,
    remote: PreferenceSyncRecord,
) -> dict[str, Any]:
    """Compare two sync records field by field."""
    changes: list[dict[str, Any]] = []
    for field_name in SYNC_FIELDS:
        before = getattr(local.snapshot, field_name)
        after = getattr(remote.snapshot, field_name)
        if before != after:
            changes.append(
                {
                    "field": field_name,
                    "local": before,
                    "remote": after,
                }
            )
    revision_gap = remote.revision - local.revision
    return {
        "changes": changes,
        "fields": [item["field"] for item in changes],
        "local_checksum": local.checksum,
        "remote_checksum": remote.checksum,
        "same_checksum": local.checksum == remote.checksum,
        "revision_gap": revision_gap,
        "remote_newer": revision_gap > 0,
    }


def merge_snapshots(
    local: PreferenceSnapshot,
    remote: PreferenceSnapshot,
    *,
    strategy: SyncStrategy,
    fields: Sequence[str] = SYNC_FIELDS,
) -> tuple[PreferenceSnapshot, tuple[str, ...], tuple[str, ...]]:
    """Merge two snapshots under an explicit conflict strategy."""
    if strategy == SyncStrategy.REJECT:
        return local, (), ("sync rejected by strategy",)
    if strategy == SyncStrategy.REMOTE_WINS:
        return replace(remote, revision=max(local.revision, remote.revision) + 1), (), ()
    if strategy == SyncStrategy.LOCAL_WINS:
        return replace(local, revision=max(local.revision, remote.revision) + 1), (), ()
    changes: list[str] = []
    conflicts: list[str] = []
    values: dict[str, Any] = {}
    for field_name in fields:
        before = getattr(local, field_name)
        after = getattr(remote, field_name)
        if before == after:
            values[field_name] = before
            continue
        if field_name == "shortcuts":
            merged_shortcuts = dict(before)
            for action, keys in after.items():
                if action in merged_shortcuts and merged_shortcuts[action] != keys:
                    conflicts.append(f"shortcut conflict: {action}")
                else:
                    merged_shortcuts[action] = keys
            values[field_name] = merged_shortcuts
            changes.append("shortcuts")
            continue
        if getattr(local, "revision", 1) == getattr(remote, "revision", 1):
            conflicts.append(f"simultaneous edit of {field_name}")
            values[field_name] = before
            continue
        values[field_name] = after
        changes.append(field_name)
    merged = replace(
        local,
        **values,
        revision=max(local.revision, remote.revision) + 1,
    )
    return merged, tuple(changes), tuple(conflicts)


class SyncStore:
    """In-memory store for versioned preference records."""

    def __init__(self) -> None:
        self._records: dict[str, PreferenceSyncRecord] = {}

    def load(self, profile: str = "default") -> PreferenceSyncRecord:
        """Return a stored record or a default record."""
        found = self._records.get(profile)
        if found is not None:
            return found
        return record_from_snapshot(default_preferences(), profile=profile)

    def save(self, record: PreferenceSyncRecord) -> PreferenceSyncRecord:
        """Persist a record and return it."""
        self._records[record.profile] = record
        return record

    def profiles(self) -> tuple[str, ...]:
        """Return stored profile names."""
        return tuple(sorted(self._records))

    def clear(self) -> None:
        """Remove every stored record."""
        self._records.clear()


class PreferenceSyncService:
    """Coordinate preference reads, updates, and cross-feature sync."""

    def __init__(self, store: SyncStore | None = None) -> None:
        self.store = store or SyncStore()

    def current(self, profile: str = "default") -> PreferenceSyncRecord:
        """Return the current record for a profile."""
        return self.store.load(profile)

    def effective(self, profile: str = "default") -> dict[str, Any]:
        """Return the effective settings including unified appearance."""
        record = self.current(profile)
        appearance = appearance_from_snapshot(record.snapshot)
        return {
            "record": record.as_dict(),
            "appearance": appearance.as_dict(),
            "css": appearance_css(appearance),
            "signature": snapshot_signature(record.snapshot),
            "features": sorted(self.store.profiles()),
            "valid": record.checksum == checksum(record.snapshot),
        }

    def update(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
        source: str = "local",
    ) -> PreferenceSyncRecord:
        """Merge a preference patch into the current record."""
        current = self.current(profile).snapshot
        merged = dict(current.as_dict())
        merged.update(dict(payload))
        merged["revision"] = current.revision + 1
        snapshot = snapshot_from_payload(merged)
        return self.store.save(record_from_snapshot(snapshot, profile=profile, source=source))

    def replace(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
        source: str = "request",
    ) -> PreferenceSyncRecord:
        """Replace the stored snapshot with a complete validated payload."""
        snapshot = snapshot_from_payload(payload)
        return self.store.save(record_from_snapshot(snapshot, profile=profile, source=source))

    def sync(
        self,
        payload: Mapping[str, Any],
        *,
        profile: str = "default",
        strategy: SyncStrategy = SyncStrategy.MERGE,
        source: str = "remote",
    ) -> SyncReport:
        """Synchronize a remote preference record into a local profile."""
        local = self.current(profile)
        remote = snapshot_from_payload(payload.get("preferences") or payload)
        remote_record = record_from_snapshot(remote, profile=profile, source=source)
        difference = diff_records(local, remote_record)
        merged, changes, conflicts = merge_snapshots(local.snapshot, remote, strategy=strategy)
        applied = not conflicts
        final = replace(
            remote_record,
            snapshot=merged,
            revision=merged.revision,
            checksum=checksum(merged),
            source=source,
        )
        if applied:
            self.store.save(final)
        warnings = []
        if not difference["remote_newer"]:
            warnings.append("remote revision is not newer than local")
        if strategy == SyncStrategy.REJECT:
            warnings.append("remote changes were rejected")
        return SyncReport(
            strategy=strategy,
            applied=applied,
            record=final,
            changes=changes,
            conflicts=conflicts,
            warnings=tuple(warnings),
        )

    def set_appearance(
        self,
        appearance: UnifiedAppearance,
        *,
        profile: str = "default",
    ) -> PreferenceSyncRecord:
        """Apply a unified appearance record to a profile."""
        snapshot = apply_appearance(self.current(profile).snapshot, appearance)
        return self.store.save(record_from_snapshot(snapshot, profile=profile))

    def reset(self, *, profile: str = "default") -> PreferenceSyncRecord:
        """Reset a profile to validated defaults."""
        return self.store.save(record_from_snapshot(default_preferences(), profile=profile))

    def export(self, *, profile: str = "default") -> dict[str, Any]:
        """Export a profile as a portable payload."""
        return self.current(profile).as_dict()


def shortcut_payload(shortcuts: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """Normalize shortcut bindings for a preference payload."""
    return {str(key): list(normalize_binding(value)) for key, value in shortcuts.items()}


def shortcut_objects(shortcuts: Mapping[str, Sequence[str]]) -> tuple[Shortcut, ...]:
    """Build V2 shortcut records from a preference payload."""
    return tuple(
        Shortcut(action=str(key), keys=normalize_binding(value), label=str(key).replace("_", " "))
        for key, value in shortcuts.items()
    )


def motion_equivalence(mode: MotionMode | str) -> dict[str, Any]:
    """Describe how a motion mode keeps content usable."""
    selected = mode if isinstance(mode, MotionMode) else MotionMode(str(mode).lower())
    durations = MOTION_DURATIONS[selected]
    return {
        "mode": selected.value,
        "durations": dict(durations),
        "content_hidden": False,
        "transitions_disabled": selected != MotionMode.FULL,
        "equivalent_focus_order": True,
    }


def supported_focus_modes() -> tuple[str, ...]:
    """Return the focus scopes recognized by the unified control."""
    return tuple(sorted(mode.value for mode in FocusMode))


__all__ = [
    "DEFAULT_APPEARANCE",
    "MOTION_DURATIONS",
    "SYNC_FIELDS",
    "SyncStore",
    "UnifiedAppearance",
    "appearance_css",
    "appearance_from_snapshot",
    "apply_appearance",
    "checksum",
    "diff_records",
    "merge_snapshots",
    "motion_equivalence",
    "record_from_snapshot",
    "shortcut_objects",
    "shortcut_payload",
    "snapshot_from_payload",
    "supported_focus_modes",
]
