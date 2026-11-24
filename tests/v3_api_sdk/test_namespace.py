"""Extensions namespace route registration and behavior."""

from __future__ import annotations

from typing import Any

import pytest

from redscribe.v3.api.envelope import is_envelope
from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.pagination import decode_cursor
from redscribe.v3.api.router import V3Router, default_router
from redscribe.v3.api_sdk.manifest import parse_manifest
from redscribe.v3.api_sdk.service import ExtensionService


def test_register_adds_all_extension_routes(router: V3Router) -> None:
    routes = {f"{item.namespace}.{item.action}" for item in router.routes()}
    expected = {
        "extensions.validate",
        "extensions.schema",
        "extensions.example",
        "extensions.contracts",
        "extensions.safety",
        "extensions.health",
        "extensions.capabilities",
        "extensions.list",
        "extensions.get",
        "extensions.install",
        "extensions.remove",
        "extensions.routes",
    }
    assert expected <= routes
    assert "extensions" in router.namespaces()
    assert len(expected) == 12


def test_read_routes_return_envelopes(router: V3Router, sample_manifest: dict[str, Any]) -> None:
    validate = router.dispatch("extensions", "validate", {"manifest": sample_manifest})
    assert is_envelope(validate)
    assert validate["data"]["valid"] is True
    assert validate["meta"]["api_version"] == "3.0"
    assert router.dispatch("extensions", "schema")["data"]["executes_code"] is False
    assert router.dispatch("extensions", "example")["data"]["id"] == "example.panel"
    assert router.dispatch("extensions", "health")["data"]["status"] == "ok"
    assert router.dispatch("extensions", "contracts")["data"]["write_requires_opt_in"] is True
    assert router.dispatch("extensions", "routes")["data"]["version"] == "3.0"


def test_list_route_uses_b00_pagination(
    router: V3Router, writable_service: ExtensionService
) -> None:
    for index in range(3):
        document = dict(writable_service.example())
        document["id"] = f"test.ext{index}"
        writable_service.store.install(parse_manifest(document))
    envelope = router.dispatch("extensions", "list", {"offset": 0, "size": 2})
    assert envelope["meta"]["page"]["total"] == 3
    assert envelope["data"]["next_cursor"]
    assert decode_cursor(envelope["data"]["next_cursor"]).offset == 2
    last = router.dispatch("extensions", "list", {"offset": 2, "size": 2})
    assert last["data"]["next_cursor"] == ""
    assert len(last["data"]["extensions"]) == 1
    with pytest.raises(V3Error):
        router.dispatch("extensions", "list", {"cursor": "tampered"})


def test_get_install_and_remove_routes(
    router: V3Router,
    writable_service: ExtensionService,
    sample_manifest: dict[str, Any],
) -> None:
    installed = router.dispatch(
        "extensions", "install", {"manifest": sample_manifest, "allow_write": True}
    )
    assert installed["data"]["extension"]["id"] == "example.panel"
    fetched = router.dispatch("extensions", "get", {"id": "example.panel"})
    assert fetched["meta"]["etag"]
    conditional = router.dispatch(
        "extensions",
        "get",
        {"id": "example.panel"},
        {"If-None-Match": fetched["meta"]["etag"]},
    )
    assert conditional["data"]["not_modified"] is True
    with pytest.raises(V3Error):
        router.dispatch("extensions", "install", {"manifest": sample_manifest})
    removed = router.dispatch("extensions", "remove", {"id": "example.panel", "allow_write": True})
    assert removed["data"]["removed"] is True
    with pytest.raises(V3Error):
        router.dispatch("extensions", "get", {"id": "example.panel"})


def test_capabilities_route(router: V3Router) -> None:
    data = router.dispatch(
        "extensions",
        "capabilities",
        {"required": ["findings", "extensions", "not-real"]},
    )["data"]
    assert data["granted"] is False
    assert "not-real" in data["denied"]
    denied = [item for item in data["decisions"] if not item["granted"]]
    assert any(item["name"] == "not-real" for item in denied)
    allowed = router.dispatch("extensions", "capabilities", {"required": ["extensions"]})["data"]
    assert allowed["granted"] is True
    with pytest.raises(V3Error):
        router.dispatch("extensions", "capabilities", {"required": "extensions"})


def test_safety_route_reports_clean_sources(router: V3Router) -> None:
    report = router.dispatch("extensions", "safety")["data"]
    assert report["clean"] is True
    assert report["findings"] == []
    assert report["checked_at"].endswith("Z")


def test_install_denied_when_capability_disabled(
    router: V3Router, sample_manifest: dict[str, Any]
) -> None:
    with pytest.raises(V3Error):
        router.dispatch(
            "extensions",
            "install",
            {"manifest": sample_manifest, "allow_write": True},
        )


def test_default_router_discovers_extensions() -> None:
    router = default_router()
    assert router.get("extensions", "schema") is not None
    assert router.dispatch("extensions", "health")["data"]["status"] == "ok"
