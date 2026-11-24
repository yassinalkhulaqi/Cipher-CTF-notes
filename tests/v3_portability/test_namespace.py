"""Tests for the sync namespace registered through the V3 router."""

from __future__ import annotations

import base64

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import V3Router
from redscribe.v3.clock import FixedClock
from redscribe.v3.namespaces import install_namespaces, namespace_names
from redscribe.v3.namespaces import sync as sync_namespace
from redscribe.v3.portability.service import PortabilityService
from tests.v3_portability.conftest import TEST_PASSPHRASE, make_entity


@pytest.fixture
def router() -> V3Router:
    """Fresh router with a cheap-KDF portability service."""
    instance = V3Router()
    service = PortabilityService(clock=FixedClock(1_700_000_000.0), kdf_iterations=1_000)
    sync_namespace.register(instance, service)
    return instance


def test_register_adds_all_declared_actions(router: V3Router) -> None:
    for action in sync_namespace.actions():
        route = router.get("sync", action)
        assert route is not None
        assert route.path == f"/api/v3/sync/{action}"
    assert router.size() == len(sync_namespace.actions())


def test_namespace_is_discovered_dynamically() -> None:
    assert "sync" in namespace_names()
    discovered = V3Router()
    installed = install_namespaces(discovered)
    assert installed is True
    assert discovered.get("sync", "health") is not None
    assert discovered.get("system", "info") is not None


def test_duplicate_registration_is_rejected(router: V3Router) -> None:
    with pytest.raises(V3Error, match="Route already registered"):
        sync_namespace.register(router)


def test_health_and_reasons_routes(router: V3Router) -> None:
    health = router.dispatch("sync", "health")
    assert health["available"]
    reasons = router.dispatch("sync", "reasons")
    assert len(reasons["reasons"]) >= 10
    assert any(item["code"] == "delete_modify" for item in reasons["reasons"])


def test_vector_compare_route(router: V3Router) -> None:
    result = router.dispatch(
        "sync",
        "vectors.compare",
        {"local": {"alpha": 2}, "remote": {"beta": 1}},
    )
    assert result["relation"] == "concurrent"
    assert result["merged"] == {"alpha": 2, "beta": 1}


def test_device_routes(router: V3Router) -> None:
    registered = router.dispatch(
        "sync", "device.register", {"device_id": "beta", "label": "Beta laptop"}
    )
    assert registered["device_id"] == "beta"
    trusted = router.dispatch("sync", "device.trust", {"device_id": "beta"})
    assert trusted["trusted"] is True
    assert router.dispatch("sync", "devices")["count"] == 2


def test_bundle_routes(router: V3Router) -> None:
    created = router.dispatch(
        "sync",
        "bundle.create",
        {
            "entities": [make_entity("note:1", title="Secret").as_dict()],
            "links": [],
            "passphrase": TEST_PASSPHRASE,
        },
    )
    bundle_id = created["bundle_id"]
    assert router.dispatch("sync", "bundle.inspect", {"bundle_id": bundle_id})["entity_count"] == 1
    opened = router.dispatch(
        "sync", "bundle.open", {"bundle_id": bundle_id, "passphrase": TEST_PASSPHRASE}
    )
    assert opened["entity_payloads"][0]["record"]["title"] == "Secret"
    verified = router.dispatch(
        "sync", "bundle.verify", {"bundle_id": bundle_id, "passphrase": TEST_PASSPHRASE}
    )
    assert verified["receipt"]["ok"]
    receipt_id = verified["receipt"]["receipt_id"]
    assert router.dispatch("sync", "receipt.get", {"receipt_id": receipt_id})["ok"]
    assert router.dispatch("sync", "receipt.list")["count"] == 1


def test_bundle_plan_route(router: V3Router) -> None:
    preview = router.dispatch(
        "sync",
        "bundle.plan",
        {"entities": [make_entity("note:1").as_dict()], "links": []},
    )
    assert preview["operation"] == "bundle.create"
    assert preview["counts"]["entities"] == 1


def test_conflict_detection_route(router: V3Router) -> None:
    base = make_entity("note:1", title="Base")
    local = base.apply_fields({"title": "Local"}, vector=base.vector.bump("alpha"))
    remote = base.apply_fields({"title": "Remote"}, vector=base.vector.bump("beta"))
    report = router.dispatch(
        "sync",
        "conflicts.detect",
        {
            "base": [base.as_dict()],
            "local": [local.as_dict()],
            "remote": [remote.as_dict()],
        },
    )
    assert report["count"] == 1
    assert report["reasons"] == ["field_both_edited"]


def test_merge_preview_and_resolve_routes(router: V3Router) -> None:
    base = make_entity("note:1", title="Base")
    local = base.apply_fields({"title": "Local"}, vector=base.vector.bump("alpha"))
    remote = base.apply_fields({"title": "Remote"}, vector=base.vector.bump("beta"))
    created = router.dispatch(
        "sync",
        "bundle.create",
        {"entities": [remote.as_dict()], "passphrase": TEST_PASSPHRASE},
    )
    preview = router.dispatch(
        "sync",
        "merge.preview",
        {
            "bundle_id": created["bundle_id"],
            "passphrase": TEST_PASSPHRASE,
            "base": [base.as_dict()],
            "local": [local.as_dict()],
        },
    )
    assert not preview["valid"]
    resolved = router.dispatch(
        "sync",
        "conflicts.resolve",
        {"preview_id": preview["preview_id"], "decisions": {"note:1": "keep_local"}},
    )
    assert resolved["merge"]["conflicts"] == []
    assert resolved["ledger_intact"]


def test_transfer_routes(router: V3Router) -> None:
    created = router.dispatch(
        "sync",
        "bundle.create",
        {"entities": [make_entity("note:1").as_dict()], "passphrase": TEST_PASSPHRASE},
    )
    started = router.dispatch(
        "sync", "transfer.start", {"bundle_id": created["bundle_id"], "chunk_size": 128}
    )
    transfer_id = started["transfer_id"]
    assert router.dispatch("sync", "transfer.status", {"transfer_id": transfer_id})["percent"] == 0
    paused = router.dispatch("sync", "transfer.pause", {"transfer_id": transfer_id})
    assert paused["state"] == "paused"
    resumed = router.dispatch("sync", "transfer.resume", {"transfer_id": transfer_id})
    assert resumed["state"] == "active"
    checkpoint = router.dispatch("sync", "transfer.checkpoint", {"transfer_id": transfer_id})
    assert checkpoint["resumable"]


def test_error_envelope_mapping_for_missing_field(router: V3Router) -> None:
    with pytest.raises(V3Error) as error:
        router.dispatch("sync", "bundle.inspect", {})
    assert error.value.code.value == "invalid_type"
    with pytest.raises(V3Error):
        router.dispatch("sync", "bundle.inspect", {"bundle_id": "bundle_unknown"})


def test_bad_chunk_index_is_rejected(router: V3Router) -> None:
    created = router.dispatch(
        "sync",
        "bundle.create",
        {"entities": [make_entity("note:1").as_dict()], "passphrase": TEST_PASSPHRASE},
    )
    started = router.dispatch("sync", "transfer.start", {"bundle_id": created["bundle_id"]})
    with pytest.raises(V3Error):
        router.dispatch(
            "sync",
            "transfer.chunk",
            {
                "transfer_id": started["transfer_id"],
                "index": -1,
                "chunk": base64.b64encode(b"x").decode("ascii"),
            },
        )
