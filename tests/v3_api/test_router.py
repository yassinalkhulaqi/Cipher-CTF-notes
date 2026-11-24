"""Tests for additive V3 route registration and namespace discovery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import RouteSpec, V3Router, register_system_routes
from redscribe.v3.namespaces import (
    discover_modules,
    has_namespace,
    install_namespaces,
    load_namespace,
    namespace_names,
    register_all,
)


def _handler(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    return {"echo": body.get("value", ""), "header": headers.get("x-test", "")}


def test_router_add_and_dispatch() -> None:
    router = V3Router()
    spec = router.add("notes", "get", _handler, methods=("GET", "POST"))
    assert spec.path == "/api/v3/notes/get"
    assert router.get("notes", "get") == spec
    assert router.size() == 1
    assert router.namespaces() == ("notes",)
    result = router.dispatch("notes", "get", {"value": "hi"}, {"x-test": "yes"}, method="GET")
    assert result == {"echo": "hi", "header": "yes"}


def test_router_rejects_duplicates_and_unknown() -> None:
    router = V3Router()
    router.add("notes", "get", _handler)
    with pytest.raises(V3Error):
        router.add("notes", "get", _handler)
    with pytest.raises(V3Error):
        router.dispatch("notes", "missing")
    with pytest.raises(V3Error):
        router.dispatch("notes", "get", method="DELETE")


def test_router_manifest_and_system_routes() -> None:
    router = V3Router()
    register_system_routes(router)
    manifest = router.manifest()
    assert manifest["version"] == "3.0"
    assert "system" in manifest["namespaces"]
    assert any(route["public"] for route in manifest["routes"])
    assert router.dispatch("system", "health")["status"] == "ok"
    assert router.dispatch("system", "manifest")["manifest"]["version"] == "3.0"


def test_route_spec_key() -> None:
    spec = RouteSpec(namespace="a", action="b", handler=_handler)
    assert spec.key == ("a", "b")
    assert spec.methods == ("POST",)


def test_dynamic_namespace_discovery() -> None:
    names = namespace_names()
    assert "system" in names
    assert has_namespace("system")
    assert not has_namespace("does_not_exist")
    assert discover_modules()
    module = load_namespace("system")
    assert callable(module.register)
    with pytest.raises(ValueError):
        load_namespace("does_not_exist")


def test_register_all_and_idempotent_install() -> None:
    direct = V3Router()
    assert register_all(direct) >= 1
    assert direct.size() > 0
    router = V3Router()
    assert install_namespaces(router) is True
    original = router.size()
    assert install_namespaces(router) is False
    assert router.size() == original


def test_router_install_namespaces_is_per_instance() -> None:
    first = V3Router()
    second = V3Router()
    first.install_namespaces()
    assert first.size() > 0
    assert second.size() == 0
    second.install_namespaces()
    assert second.size() == first.size()


def test_error_code_constants() -> None:
    assert V3ErrorCode.UNKNOWN_ROUTE.value == "unknown_route"
    assert V3ErrorCode.PRECONDITION_FAILED.value == "precondition_failed"
