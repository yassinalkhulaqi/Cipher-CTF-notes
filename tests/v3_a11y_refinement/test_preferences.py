"""Preference synchronization and unified theme/motion control tests."""

from __future__ import annotations

from dataclasses import replace

from redscribe.v2.a11y.models import Direction
from redscribe.v2.a11y.preferences import default_preferences
from redscribe.v3.a11y_refinement.models import MotionMode, SyncStrategy
from redscribe.v3.a11y_refinement.preferences import (
    DEFAULT_APPEARANCE,
    SyncStore,
    UnifiedAppearance,
    appearance_css,
    appearance_from_snapshot,
    apply_appearance,
    checksum,
    diff_records,
    merge_snapshots,
    motion_equivalence,
    record_from_snapshot,
    shortcut_objects,
    shortcut_payload,
    snapshot_from_payload,
    supported_focus_modes,
)


def test_checksum_is_stable_and_sensitive() -> None:
    snapshot = default_preferences()
    first = checksum(snapshot)
    assert first == checksum(snapshot)
    assert len(first) == 16
    assert checksum(replace(snapshot, locale="ar")) != first
    assert checksum(replace(snapshot, updated_at="later")) == first


def test_record_from_snapshot_and_defaults() -> None:
    snapshot = replace(default_preferences(), revision=3)
    record = record_from_snapshot(snapshot, profile="work", source="remote", tags=("v3",))
    assert record.profile == "work"
    assert record.revision == 3
    assert record.source == "remote"
    assert record.tags == ("v3",)
    assert record.checksum == checksum(snapshot)
    assert record.as_dict()["preferences"]["revision"] == 3


def test_appearance_from_snapshot_and_apply() -> None:
    snapshot = replace(
        default_preferences(),
        theme="light",
        reduce_motion=True,
        high_contrast=True,
        font_scale=1.25,
        direction=Direction.RTL,
    )
    appearance = appearance_from_snapshot(snapshot)
    assert appearance.theme == "light"
    assert appearance.motion == MotionMode.REDUCED
    assert appearance.direction == Direction.RTL
    assert appearance.high_contrast is True
    restored = apply_appearance(snapshot, DEFAULT_APPEARANCE)
    assert restored.reduce_motion is False
    assert restored.revision == snapshot.revision + 1


def test_appearance_css_contains_theme_motion_and_focus() -> None:
    appearance = UnifiedAppearance(
        theme="graphite",
        motion=MotionMode.REDUCED,
        density="compact",
        font_scale=1.5,
        focus_ring_boost=True,
    )
    variables = appearance_css(appearance)
    assert variables["--v3-theme"] == "graphite"
    assert variables["--v3-density"] == "compact"
    assert variables["--v3-motion-normal"] == "1ms"
    assert variables["--v3-font-scale"] == "1.50"
    assert variables["--v3-focus-boost"] == "1"


def test_diff_records_reports_field_changes() -> None:
    local = record_from_snapshot(replace(default_preferences(), revision=2))
    remote = record_from_snapshot(
        replace(default_preferences(), locale="ar", theme="light", revision=5),
        source="remote",
    )
    diff = diff_records(local, remote)
    assert diff["fields"] == ["locale", "theme"]
    assert diff["revision_gap"] == 3
    assert diff["remote_newer"] is True
    assert diff["same_checksum"] is False
    assert diff_records(local, local)["changes"] == []


def test_merge_snapshots_strategies() -> None:
    local = default_preferences()
    remote = replace(local, locale="ar", revision=local.revision + 2)
    remote_wins, changes, conflicts = merge_snapshots(
        local, remote, strategy=SyncStrategy.REMOTE_WINS
    )
    assert remote_wins.locale == "ar"
    assert changes == ()
    assert conflicts == ()
    local_wins, _, _ = merge_snapshots(local, remote, strategy=SyncStrategy.LOCAL_WINS)
    assert local_wins.locale == "en"
    rejected, _, reasons = merge_snapshots(local, remote, strategy=SyncStrategy.REJECT)
    assert rejected == local
    assert reasons


def test_merge_snapshots_merges_fields_and_flags_conflicts() -> None:
    local = replace(default_preferences(), revision=1)
    older = replace(local, locale="ar", revision=1)
    merged, changes, conflicts = merge_snapshots(local, older, strategy=SyncStrategy.MERGE)
    assert any("locale" in item for item in conflicts)
    assert merged.locale == "en"
    assert merged.revision == 2
    newer = replace(local, locale="ar", revision=4)
    merged, changes, conflicts = merge_snapshots(local, newer, strategy=SyncStrategy.MERGE)
    assert "locale" in changes
    assert conflicts == ()
    assert merged.locale == "ar"


def test_merge_snapshots_combines_shortcuts() -> None:
    local = replace(default_preferences(), shortcuts={"save": ["ctrl", "s"]}, revision=2)
    remote = replace(
        default_preferences(),
        shortcuts={"save": ["ctrl", "s"], "find": ["ctrl", "f"]},
        revision=5,
    )
    merged, changes, conflicts = merge_snapshots(local, remote, strategy=SyncStrategy.MERGE)
    assert "find" in merged.shortcuts
    assert "shortcuts" in changes
    assert conflicts == ()
    diverged = replace(remote, shortcuts={"save": ["ctrl", "alt", "s"]}, revision=5)
    merged, _, conflicts = merge_snapshots(local, diverged, strategy=SyncStrategy.MERGE)
    assert any("shortcut" in item for item in conflicts)
    assert merged.shortcuts["save"] == ["ctrl", "s"]


def test_sync_store_crud() -> None:
    store = SyncStore()
    assert store.profiles() == ()
    first = store.load("default")
    assert first.profile == "default"
    store.save(record_from_snapshot(default_preferences(), profile="work"))
    assert store.profiles() == ("work",)
    store.clear()
    assert store.profiles() == ()


def test_snapshot_from_payload_validates() -> None:
    snapshot = snapshot_from_payload({"locale": "de-DE", "theme": "light", "revision": 2})
    assert snapshot.locale == "de-DE"
    try:
        snapshot_from_payload({"font_scale": 99})
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid font scale to be rejected")


def test_service_update_replace_and_reset() -> None:
    from redscribe.v3.a11y_refinement.preferences import PreferenceSyncService

    service = PreferenceSyncService(SyncStore())
    assert service.effective()["valid"] is True
    updated = service.update({"locale": "ar", "theme": "light"}, profile="desk")
    assert updated.snapshot.locale == "ar"
    assert updated.snapshot.theme == "light"
    replaced = service.replace({"locale": "fr", "theme": "graphite"}, profile="desk")
    assert replaced.snapshot.locale == "fr"
    reset = service.reset(profile="desk")
    assert reset.snapshot.locale == "en"
    assert service.effective(profile="desk")["appearance"]["theme"] == "graphite"


def test_service_sync_applies_remote_changes() -> None:
    from redscribe.v3.a11y_refinement.preferences import PreferenceSyncService

    service = PreferenceSyncService(SyncStore())
    report = service.sync(
        {"preferences": {"locale": "fa", "theme": "light", "revision": 9}},
        strategy=SyncStrategy.MERGE,
    )
    assert report.applied is True
    assert report.record.snapshot.locale == "fa"
    assert "locale" in report.changes
    assert service.current().snapshot.locale == "fa"


def test_service_sync_can_reject_changes() -> None:
    from redscribe.v3.a11y_refinement.preferences import PreferenceSyncService

    service = PreferenceSyncService(SyncStore())
    report = service.sync(
        {"preferences": {"locale": "ja", "revision": 8}},
        strategy=SyncStrategy.REJECT,
    )
    assert report.applied is False
    assert service.current().snapshot.locale == "en"
    assert report.warnings


def test_service_set_appearance_updates_snapshot() -> None:
    from redscribe.v3.a11y_refinement.preferences import PreferenceSyncService

    service = PreferenceSyncService(SyncStore())
    appearance = UnifiedAppearance(theme="light", motion=MotionMode.OFF)
    record = service.set_appearance(appearance)
    assert record.snapshot.theme == "light"
    assert record.snapshot.reduce_motion is True
    assert service.effective()["css"]["--v3-motion-slow"] == "0ms"


def test_motion_equivalence_keeps_content_usable() -> None:
    full = motion_equivalence(MotionMode.FULL)
    reduced = motion_equivalence("reduced")
    off = motion_equivalence(MotionMode.OFF)
    assert full["transitions_disabled"] is False
    assert reduced["content_hidden"] is False
    assert off["durations"]["normal"] == "0ms"
    assert reduced["equivalent_focus_order"] is True


def test_shortcut_helpers() -> None:
    payload = shortcut_payload({"save": ["Control", "S"], "find": "Ctrl+F"})
    assert payload == {"save": ["ctrl", "s"], "find": ["ctrl", "f"]}
    shortcuts = shortcut_objects(payload)
    assert len(shortcuts) == 2
    assert shortcuts[0].keys == ("ctrl", "s")
    assert "editor" in supported_focus_modes()
