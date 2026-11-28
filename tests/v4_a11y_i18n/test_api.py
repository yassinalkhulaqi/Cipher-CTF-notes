"""API envelopes, capability checks, events, and snapshot persistence tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from itertools import count
from typing import Any

import pytest

from redscribe.v4.a11y_i18n.api import (
    EMPTY_STATES,
    ROUTE_NAME,
    ROUTE_PREFIX,
    SAFE_EVENT_KEYS,
    AccessibilityEndpoint,
    default_endpoint,
    empty_state,
    register,
    register_endpoint,
)
from redscribe.v4.a11y_i18n.service import I18nCatalog, MotionPolicyResolver, TourEngine
from redscribe.v4.a11y_i18n.storage import (
    CatalogIndex,
    PreferenceSnapshot,
    PreferenceSnapshotStore,
    StorageError,
    catalog_checksum,
    export_bundle,
    require_name,
)
from redscribe.v4.a11y_i18n.types import (
    Direction,
    LocaleCatalog,
    MessageId,
    MotionPolicy,
    MotionPreference,
    UiDescriptor,
)
from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate, FeatureRequirement
from redscribe.v4.clock import Clock
from redscribe.v4.contracts import Capability, CapabilitySet
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.preferences import Preferences


def frozen_clock() -> Clock:
    return Clock(frozen_at=datetime(2026, 11, 28, 12, 30, tzinfo=timezone.utc))


def french_catalog() -> LocaleCatalog:
    return LocaleCatalog(
        "fr",
        Direction.LTR,
        {
            MessageId.SAVE: "Enregistrer",
            MessageId.LOADING: "Chargement de {items} éléments",
            MessageId.ITEMS_COUNT: "{count} élément",
        },
    )


def arabic_catalog() -> LocaleCatalog:
    return LocaleCatalog("ar", Direction.RTL, {MessageId.SAVE: "حفظ"})


def build_endpoint(
    capabilities: CapabilitySet | None = None,
    gate: FeatureGate | None = None,
) -> tuple[AccessibilityEndpoint, InMemoryOutbox, EventBus]:
    outbox = InMemoryOutbox()
    bus = EventBus(outbox=outbox)
    counter: Iterator[int] = count(1)
    store = PreferenceSnapshotStore(clock=frozen_clock())
    catalog = I18nCatalog()
    catalog.register(french_catalog())
    catalog.register(arabic_catalog())
    index = CatalogIndex()
    for locale in catalog.available_locales():
        index.register(catalog.catalog_for(locale))
    granted = capabilities or CapabilitySet.full()
    endpoint = AccessibilityEndpoint(
        store=store,
        catalog=catalog,
        catalog_index=index,
        resolver=MotionPolicyResolver(),
        tour=TourEngine(),
        capabilities=granted,
        gate=gate or FeatureGate(granted),
        bus=bus,
        id_factory=lambda: f"req-{next(counter):04d}",
    )
    return endpoint, outbox, bus


def data(envelope: Mapping[str, Any]) -> Any:
    assert "error" not in envelope, envelope
    assert "data" in envelope
    assert "meta" in envelope
    return envelope["data"]


def error_code(envelope: Mapping[str, Any]) -> str:
    assert "error" in envelope, envelope
    return str(envelope["error"]["code"])


def test_get_envelope_shape_and_meta() -> None:
    endpoint, _, _ = build_endpoint()
    envelope = endpoint.handle_get()
    payload = data(envelope)
    assert envelope["meta"]["version"] == "v4"
    assert envelope["meta"]["request_id"] == "req-0001"
    assert payload["feature_enabled"] is True
    assert payload["rules"][0]["id"] == "missing-label"
    assert payload["locales"] == ["ar", "en", "fr"]
    assert payload["directions"]["ar"] == "rtl"
    assert set(payload["empty_states"]) == {"issues", "snapshots", "tour"}
    assert payload["tour_step"]["id"] == "tour-controls"
    assert payload["event_count"] == 0


def test_get_returns_deterministic_request_ids() -> None:
    endpoint, _, _ = build_endpoint()
    first = endpoint.handle_get()["meta"]["request_id"]
    second = endpoint.handle_get()["meta"]["request_id"]
    assert (first, second) == ("req-0001", "req-0002")


def test_get_envelope_lists_capabilities_and_actions() -> None:
    endpoint, _, _ = build_endpoint(CapabilitySet(frozenset({Capability.READ, Capability.WRITE})))
    payload = data(endpoint.handle_get())
    assert payload["capabilities"] == ["read", "write"]
    assert "snapshot-save" in payload["actions"]
    assert "tour" in payload["actions"]


def test_get_denied_without_read_capability() -> None:
    endpoint, _, _ = build_endpoint(CapabilitySet(frozenset({Capability.WRITE})))
    envelope = endpoint.handle_get()
    assert error_code(envelope) == "forbidden"
    assert "error" in envelope
    assert "data" not in envelope


def test_get_denied_when_feature_disabled() -> None:
    capabilities = CapabilitySet.full()
    gate = FeatureGate(
        capabilities,
        {FeatureFlag.A11Y_I18N: FeatureRequirement(FeatureFlag.A11Y_I18N, min_version="v5")},
    )
    endpoint, _, _ = build_endpoint(capabilities, gate)
    assert error_code(endpoint.handle_get()) == "forbidden"


def test_patch_denied_without_write_capability() -> None:
    endpoint, _, _ = build_endpoint(CapabilitySet(frozenset({Capability.READ})))
    assert error_code(endpoint.handle_patch({"action": "motion", "motion": "off"})) == "forbidden"


def test_patch_rejects_non_mapping_body() -> None:
    endpoint, _, _ = build_endpoint()
    assert error_code(endpoint.handle_patch(["not", "a", "map"])) == "invalid_input"  # type: ignore[arg-type]


def test_patch_rejects_unknown_action() -> None:
    endpoint, _, _ = build_endpoint()
    envelope = endpoint.handle_patch({"action": "teleport"})
    assert error_code(envelope) == "invalid_input"
    assert "unknown action" in envelope["error"]["message"]


def test_dispatch_supports_get_and_patch() -> None:
    endpoint, _, _ = build_endpoint()
    assert data(endpoint.dispatch("get"))
    assert data(endpoint.dispatch("PATCH", {"action": "reset"}))
    assert error_code(endpoint.dispatch("POST", {})) == "invalid_input"


def test_preferences_action_updates_and_emits_event() -> None:
    endpoint, outbox, bus = build_endpoint()
    received: list[EventKind] = []
    bus.subscribe(EventKind.PREFERENCE_CHANGED, lambda event: received.append(event.kind))
    envelope = endpoint.handle_patch(
        {"action": "preferences", "preferences": {"theme": "graphite", "density": "compact"}}
    )
    result = data(envelope)
    assert result["action"] == "preferences"
    assert result["result"]["changed"] is True
    assert result["status"]["preferences"]["theme"] == "graphite"
    assert endpoint.preferences.revision == 1
    assert len(received) == 1
    records = outbox.records(EventKind.PREFERENCE_CHANGED)
    assert len(records) == 1
    assert records[0].payload["theme"] == "graphite"
    assert records[0].payload["density"] == "compact"


def test_preferences_action_accepts_flat_overrides() -> None:
    endpoint, _, _ = build_endpoint()
    envelope = endpoint.handle_patch({"action": "preferences", "locale": "fr"})
    assert data(envelope)["result"]["preferences"]["locale"] == "fr"


def test_preferences_no_change_reports_changed_false() -> None:
    endpoint, _, _ = build_endpoint()
    result = data(endpoint.handle_patch({"action": "preferences", "preferences": {}}))
    assert result["result"]["changed"] is False
    assert endpoint.preferences.revision == 0


def test_preferences_rejects_invalid_theme() -> None:
    endpoint, _, _ = build_endpoint()
    envelope = endpoint.handle_patch({"action": "preferences", "theme": "neon"})
    assert error_code(envelope) == "invalid_input"
    assert endpoint.preferences.current.theme == "light"


def test_preferences_arabic_requires_rtl_direction() -> None:
    endpoint, _, _ = build_endpoint()
    envelope = endpoint.handle_patch({"action": "preferences", "preferences": {"locale": "ar"}})
    assert error_code(envelope) == "invalid_input"
    result = data(
        endpoint.handle_patch(
            {"action": "preferences", "preferences": {"locale": "ar", "direction": "rtl"}}
        )
    )
    assert result["result"]["preferences"]["direction"] == "rtl"


def test_locale_and_direction_are_persisted() -> None:
    endpoint, _, _ = build_endpoint()
    result = data(
        endpoint.handle_patch(
            {
                "action": "preferences",
                "preferences": {"locale": "ar", "direction": "rtl"},
            }
        )
    )
    assert result["result"]["preferences"]["direction"] == "rtl"
    assert result["status"]["directions"]["ar"] == "rtl"


def test_motion_action_sets_policy_and_emits_event() -> None:
    endpoint, outbox, _ = build_endpoint()
    result = data(
        endpoint.handle_patch({"action": "motion", "motion": "subtle", "reduce_motion": True})
    )
    assert result["result"]["motion"]["preference"] == "off"
    assert result["result"]["motion"]["animated"] is False
    assert result["status"]["reduce_motion"] is True
    assert outbox.records(EventKind.PREFERENCE_CHANGED)[0].payload["action"] == "motion"


def test_motion_action_rejects_invalid_values() -> None:
    endpoint, _, _ = build_endpoint()
    assert (
        error_code(endpoint.handle_patch({"action": "motion", "motion": "fast"})) == "invalid_input"
    )
    envelope = endpoint.handle_patch({"action": "motion", "reduce_motion": "yes"})
    assert error_code(envelope) == "invalid_input"


def test_reset_action_restores_defaults() -> None:
    endpoint, _, _ = build_endpoint()
    endpoint.handle_patch({"action": "preferences", "theme": "graphite"})
    endpoint.handle_patch({"action": "motion", "motion": "off", "reduce_motion": True})
    result = data(endpoint.handle_patch({"action": "reset"}))
    assert result["result"]["reset"] is True
    assert result["result"]["preferences"]["theme"] == "light"
    assert result["status"]["reduce_motion"] is False
    assert endpoint.event_count == 3


def test_event_payload_is_filtered_to_safe_keys() -> None:
    endpoint, outbox, _ = build_endpoint()
    endpoint.handle_patch(
        {"action": "preferences", "preferences": {"theme": "graphite", "token": "secret"}}
    )
    payload = outbox.records(EventKind.PREFERENCE_CHANGED)[0].payload
    assert set(payload) <= SAFE_EVENT_KEYS
    assert "token" not in payload


def test_snapshot_save_via_api() -> None:
    endpoint, outbox, _ = build_endpoint()
    result = data(endpoint.handle_patch({"action": "snapshot-save", "name": "night mode"}))
    snapshot = result["result"]["snapshot"]
    assert snapshot["name"] == "night mode"
    assert snapshot["version"] == 1
    assert snapshot["saved_at"] == "2026-11-28T12:30:00.000Z"
    assert result["status"]["snapshots"]["total"] == 1
    assert outbox.records(EventKind.PREFERENCE_CHANGED)[0].payload["snapshot_name"] == "night mode"


def test_snapshot_duplicate_is_conflict() -> None:
    endpoint, _, _ = build_endpoint()
    endpoint.handle_patch({"action": "snapshot-save", "name": "work"})
    envelope = endpoint.handle_patch({"action": "snapshot-save", "name": "work"})
    assert error_code(envelope) == "conflict"


def test_snapshot_overwrite_increments_version() -> None:
    endpoint, _, _ = build_endpoint()
    endpoint.handle_patch({"action": "snapshot-save", "name": "work"})
    result = data(
        endpoint.handle_patch({"action": "snapshot-save", "name": "work", "overwrite": True})
    )
    assert result["result"]["snapshot"]["version"] == 2
    assert endpoint.store.revision("work") == 2


def test_snapshot_load_restores_preferences() -> None:
    endpoint, _, _ = build_endpoint()
    endpoint.handle_patch({"action": "preferences", "theme": "graphite"})
    endpoint.handle_patch({"action": "snapshot-save", "name": "saved"})
    endpoint.handle_patch({"action": "preferences", "theme": "light"})
    result = data(endpoint.handle_patch({"action": "snapshot-load", "name": "saved"}))
    assert result["result"]["snapshot"]["preferences"]["theme"] == "graphite"
    assert result["status"]["preferences"]["theme"] == "graphite"


def test_snapshot_load_missing_is_not_found() -> None:
    endpoint, _, _ = build_endpoint()
    assert (
        error_code(endpoint.handle_patch({"action": "snapshot-load", "name": "ghost"}))
        == "not_found"
    )


def test_snapshot_delete_requires_delete_capability() -> None:
    limited = CapabilitySet(frozenset({Capability.READ, Capability.WRITE}))
    endpoint, _, _ = build_endpoint(limited)
    endpoint.store.save("draft", Preferences(), MotionPolicy(MotionPreference.FULL, {}), "en")
    assert (
        error_code(endpoint.handle_patch({"action": "snapshot-delete", "name": "draft"}))
        == "forbidden"
    )


def test_snapshot_delete_via_api() -> None:
    endpoint, _, _ = build_endpoint()
    endpoint.handle_patch({"action": "snapshot-save", "name": "draft"})
    result = data(endpoint.handle_patch({"action": "snapshot-delete", "name": "draft"}))
    assert result["result"] == {"removed": "draft", "total": 0}
    assert (
        error_code(endpoint.handle_patch({"action": "snapshot-delete", "name": "draft"}))
        == "not_found"
    )


def test_audit_action_reports_issues() -> None:
    endpoint, _, _ = build_endpoint()
    descriptors = [
        UiDescriptor("btn", "button", "", True, True, 7.0).to_dict(),
        UiDescriptor("dim", "paragraph", "Text", False, True, 2.0).to_dict(),
    ]
    result = data(endpoint.handle_patch({"action": "audit", "descriptors": descriptors}))
    report = result["result"]["report"]
    assert report["descriptor_count"] == 2
    assert len(report["issues"]) == 2


def test_audit_action_rejects_bad_descriptors() -> None:
    endpoint, _, _ = build_endpoint()
    assert (
        error_code(endpoint.handle_patch({"action": "audit", "descriptors": "bad"}))
        == "invalid_input"
    )
    assert (
        error_code(endpoint.handle_patch({"action": "audit", "descriptors": [{"id": "BAD ID"}]}))
        == "invalid_input"
    )


def test_translate_action_uses_locale() -> None:
    endpoint, _, _ = build_endpoint()
    result = data(endpoint.handle_patch({"action": "translate", "message": "save", "locale": "fr"}))
    assert result["result"]["translation"]["text"] == "Enregistrer"
    assert result["result"]["translation"]["resolved_locale"] == "fr"


def test_translate_action_interpolates_params() -> None:
    endpoint, _, _ = build_endpoint()
    result = data(
        endpoint.handle_patch(
            {"action": "translate", "message": "loading", "locale": "fr", "params": {"items": 4}}
        )
    )
    assert result["result"]["translation"]["text"] == "Chargement de 4 éléments"


def test_translate_action_handles_plurals() -> None:
    endpoint, _, _ = build_endpoint()
    result = data(
        endpoint.handle_patch(
            {
                "action": "translate",
                "message": "items.count",
                "locale": "en",
                "plural": True,
                "count": 2,
            }
        )
    )
    assert result["result"]["translation"]["text"] == "2 items"


def test_translate_action_errors() -> None:
    endpoint, _, _ = build_endpoint()
    assert (
        error_code(endpoint.handle_patch({"action": "translate", "message": "nope"}))
        == "invalid_input"
    )
    assert (
        error_code(
            endpoint.handle_patch({"action": "translate", "message": "loading", "params": []})
        )
        == "invalid_input"
    )
    assert (
        error_code(
            endpoint.handle_patch(
                {"action": "translate", "message": "items.count", "plural": True, "count": "two"}
            )
        )
        == "invalid_input"
    )


def test_tour_action_flow_via_api() -> None:
    endpoint, _, _ = build_endpoint()
    started = data(endpoint.handle_patch({"action": "tour", "operation": "start"}))
    assert started["result"]["state"]["status"] == "in_progress"
    advanced = data(endpoint.handle_patch({"action": "tour", "operation": "next"}))
    assert advanced["result"]["step"]["id"] == "tour-audit"
    assert (
        data(endpoint.handle_patch({"action": "tour", "operation": "previous"}))["result"]["step"][
            "id"
        ]
        == "tour-controls"
    )
    assert (
        data(endpoint.handle_patch({"action": "tour", "operation": "skip"}))["result"]["state"][
            "status"
        ]
        == "skipped"
    )
    assert (
        data(endpoint.handle_patch({"action": "tour", "operation": "reset"}))["result"]["state"][
            "status"
        ]
        == "not_started"
    )


def test_tour_action_rejects_unknown_operation() -> None:
    endpoint, _, _ = build_endpoint()
    assert (
        error_code(endpoint.handle_patch({"action": "tour", "operation": "fly"})) == "invalid_input"
    )


def test_route_registration_uses_v4_prefix() -> None:
    endpoint, _, _ = build_endpoint()
    registry = RouteRegistry()
    register_endpoint(registry, endpoint)
    route = registry.get("/api/v4/accessibility")
    assert route is not None
    assert route.name == ROUTE_NAME
    assert route.prefix == ROUTE_PREFIX
    assert route.handler == endpoint.dispatch
    assert registry.serialize()[0]["path"] == "/api/v4/accessibility"


def test_route_registration_rejects_duplicates() -> None:
    endpoint, _, _ = build_endpoint()
    registry = RouteRegistry()
    register_endpoint(registry, endpoint)
    with pytest.raises(ValueError, match="route already registered"):
        register_endpoint(registry, endpoint)


def test_register_with_mapping() -> None:
    endpoint = default_endpoint()
    mapping: dict[str, Any] = {}
    register(mapping)
    assert mapping["/api/v4/accessibility"] == endpoint.dispatch


def test_register_with_registrar_object() -> None:
    calls: list[tuple[str, str, Callable[..., object]]] = []

    class FakeRegistry:
        def register(self, prefix: str, name: str, handler: Callable[..., object]) -> None:
            calls.append((prefix, name, handler))

    register(FakeRegistry())
    assert calls[0][0] == ROUTE_PREFIX
    assert calls[0][1] == ROUTE_NAME


def test_empty_state_lookup() -> None:
    assert empty_state("issues") is EMPTY_STATES["issues"]
    with pytest.raises(ValueError, match="unknown empty state"):
        empty_state("missing")


# -- storage adapters ---------------------------------------------------


def test_store_save_and_load_round_trip() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    policy = MotionPolicy(MotionPreference.SUBTLE, {"fast": 60})
    saved = store.save("focus", Preferences(theme="graphite"), policy, "fr")
    loaded = store.load("focus")
    assert loaded == saved
    assert loaded.preferences.theme == "graphite"
    assert loaded.motion_policy.duration_for("fast") == 60
    assert loaded.saved_at == "2026-11-28T12:30:00.000Z"
    assert loaded.version == 1
    assert PreferenceSnapshot.from_dict(saved.to_dict()) == saved


def test_store_save_requires_unique_name_and_valid_name() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    store.save("one", Preferences(), MotionPolicy(MotionPreference.FULL, {}), "en")
    with pytest.raises(StorageError, match="snapshot exists"):
        store.save("one", Preferences(), MotionPolicy(MotionPreference.FULL, {}), "en")
    with pytest.raises(StorageError, match="invalid snapshot name"):
        store.save("bad/name", Preferences(), MotionPolicy(MotionPreference.FULL, {}), "en")


def test_store_overwrite_increments_version() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    policy = MotionPolicy(MotionPreference.FULL, {})
    first = store.save("one", Preferences(), policy, "en")
    second = store.save("one", Preferences(), policy, "en", overwrite=True)
    assert first.version == 1
    assert second.version == 2
    assert store.revision("one") == 2


def test_store_load_missing_name() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    with pytest.raises(StorageError, match="snapshot not found"):
        store.load("ghost")


def test_store_remove_rename_and_clear() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    policy = MotionPolicy(MotionPreference.FULL, {})
    store.save("old", Preferences(), policy, "en")
    renamed = store.rename("old", "new")
    assert renamed.name == "new"
    assert renamed.version == 2
    assert store.get("old") is None
    assert store.get("new") == renamed
    with pytest.raises(StorageError, match="names must differ"):
        store.rename("new", "new")
    removed = store.remove("new")
    assert removed.name == "new"
    store.save("temp", Preferences(), policy, "en")
    store.clear()
    assert store.count() == 0


def test_store_rename_rejects_missing_and_existing_target() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    policy = MotionPolicy(MotionPreference.FULL, {})
    with pytest.raises(StorageError, match="snapshot not found"):
        store.rename("missing", "new")
    store.save("a", Preferences(), policy, "en")
    store.save("b", Preferences(), policy, "en")
    with pytest.raises(StorageError, match="snapshot exists"):
        store.rename("a", "b")


def test_store_index_and_names_are_sorted() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    policy = MotionPolicy(MotionPreference.FULL, {})
    store.save("zeta", Preferences(), policy, "fr")
    store.save("alpha", Preferences(), policy, "en")
    assert store.names() == ("alpha", "zeta")
    index = store.index()
    assert index.names == ("alpha", "zeta")
    assert index.locales == ("en", "fr")
    assert index.total == 2
    assert index.latest_saved_at == "2026-11-28T12:30:00.000Z"
    assert index.to_dict()["total"] == 2


def test_store_export_import_round_trip() -> None:
    first = PreferenceSnapshotStore(clock=frozen_clock())
    first.save("one", Preferences(theme="graphite"), MotionPolicy(MotionPreference.FULL, {}), "fr")
    second = PreferenceSnapshotStore(clock=frozen_clock())
    assert second.import_from(first.export()) == 1
    assert second.load("one") == first.load("one")
    assert second.import_from(first.export()) == 0


def test_store_import_rejects_bad_documents() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    with pytest.raises(StorageError, match="unsupported export version"):
        store.import_from({"version": 9})
    with pytest.raises(StorageError, match="snapshots must be a list"):
        store.import_from({"version": 1, "snapshots": "oops"})
    with pytest.raises(StorageError, match="snapshot entry must be an object"):
        store.import_from({"version": 1, "snapshots": ["oops"]})


def test_require_name_allows_spaces_and_dots() -> None:
    assert require_name("Night mode v1.0") == "Night mode v1.0"
    with pytest.raises(StorageError, match="must not be empty"):
        require_name("   ")


def test_catalog_index_registers_and_detects_changes() -> None:
    index = CatalogIndex()
    catalog = french_catalog()
    record = index.register(catalog)
    assert record.language == "fr"
    assert record.direction is Direction.LTR
    assert record.message_count == len(catalog.messages)
    assert record.checksum == catalog_checksum(catalog)
    assert not index.changed(catalog)
    assert index.get("fr") == record
    with pytest.raises(StorageError, match="catalog indexed already"):
        index.register(catalog)
    altered = catalog.with_message(MessageId.RETRY, "Réessayer")
    assert index.changed(altered)
    index.register(altered, overwrite=True)
    assert index.get("fr").checksum == catalog_checksum(altered)


def test_catalog_index_search_and_missing() -> None:
    index = CatalogIndex()
    index.register(french_catalog())
    index.register(arabic_catalog())
    assert index.locales() == ("ar", "fr")
    assert [item.locale for item in index.matching("f")] == ["fr"]
    assert index.matching("zz") == ()
    with pytest.raises(StorageError, match="catalog not indexed"):
        index.get("de")
    assert index.changed(LocaleCatalog("de", Direction.LTR, {}))
    assert index.remove("ar").locale == "ar"
    with pytest.raises(StorageError, match="catalog not indexed"):
        index.remove("ar")


def test_catalog_index_export_import() -> None:
    first = CatalogIndex()
    first.register(french_catalog())
    second = CatalogIndex()
    assert second.import_from(first.export()) == 1
    assert second.get("fr") == first.get("fr")
    with pytest.raises(StorageError, match="unsupported catalog index version"):
        second.import_from({"version": 5})
    with pytest.raises(StorageError, match="catalogs must be a list"):
        second.import_from({"version": 1, "catalogs": "bad"})
    with pytest.raises(StorageError, match="catalog entry must be an object"):
        second.import_from({"version": 1, "catalogs": ["bad"]})


def test_export_bundle_contains_both_stores() -> None:
    store = PreferenceSnapshotStore(clock=frozen_clock())
    store.save("one", Preferences(), MotionPolicy(MotionPreference.FULL, {}), "en")
    catalogs = CatalogIndex()
    catalogs.register(french_catalog())
    bundle = export_bundle(store, catalogs)
    assert bundle["schema"] == "redscribe.a11y-i18n"
    assert bundle["version"] == 1
    assert bundle["snapshots"]["snapshots"][0]["name"] == "one"
    assert bundle["catalogs"]["catalogs"][0]["locale"] == "fr"


def test_snapshot_from_dict_requires_objects() -> None:
    with pytest.raises(StorageError, match="must be objects"):
        PreferenceSnapshot.from_dict({"preferences": "no", "motion_policy": {}})


def test_catalog_record_round_trip() -> None:
    from redscribe.v4.a11y_i18n.storage import CatalogRecord

    index = CatalogIndex()
    record = index.register(french_catalog())
    assert CatalogRecord.from_dict(record.to_dict()) == record
