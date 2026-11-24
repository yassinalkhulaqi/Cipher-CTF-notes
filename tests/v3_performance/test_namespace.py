"""Performance namespace registration and route behaviour."""

from __future__ import annotations

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import V3Router
from redscribe.v3.namespaces import has_namespace, load_namespace, namespace_names
from redscribe.v3.namespaces.performance import MAX_FLUSH_EVENTS, SAMPLE_DOCUMENTS, register

ACTIONS = ("benchmark", "budgets", "fixture", "flush", "index_stats", "plan")


def new_router() -> V3Router:
    router = V3Router()
    register(router)
    return router


def test_discovery_finds_performance_namespace() -> None:
    assert "performance" in namespace_names()
    assert has_namespace("performance")
    module = load_namespace("performance")
    assert callable(module.register)


def test_register_adds_all_actions() -> None:
    router = new_router()
    assert router.namespaces() == ("performance",)
    assert tuple(route.action for route in router.routes()) == ACTIONS
    assert router.get("performance", "benchmark") is not None
    assert router.dispatch("performance", "budgets")["budgets"]
    manifest = router.manifest()
    assert any(route["path"] == "/api/v3/performance/flush" for route in manifest["routes"])


def test_duplicate_registration_is_rejected() -> None:
    router = new_router()
    with pytest.raises(V3Error, match="already registered"):
        register(router)


def test_budgets_route_lists_budgets() -> None:
    router = new_router()
    payload = router.dispatch("performance", "budgets")
    names = [item["name"] for item in payload["budgets"]]
    assert "first_search" in names
    assert "graph_deferred_frame" in names
    assert len(names) == 7


def test_fixture_route_is_bounded() -> None:
    router = new_router()
    payload = router.dispatch(
        "performance", "fixture", {"notes": 40, "findings": 20, "evidence": 10}
    )
    assert payload["notes"] == 40
    assert payload["findings"] == 20
    assert payload["evidence"] == 10
    assert len(payload["fingerprint"]) == 24


def test_index_stats_route_returns_a_plan() -> None:
    router = new_router()
    payload = router.dispatch("performance", "index_stats", {"notes": 40})
    assert payload["documents"] == SAMPLE_DOCUMENTS
    assert payload["generation"] == 1
    assert payload["plan"]["nodes"]
    assert payload["plan"]["fingerprint"]


def test_plan_route_explains_plans() -> None:
    router = new_router()
    payload = router.dispatch(
        "performance", "plan", {"notes": 40, "findings": 20, "evidence": 10, "seed": 5}
    )
    lines = payload["explain"]
    assert len(lines) >= 2
    assert any("total modeled cost" in line for line in lines)


def test_benchmark_route_returns_report_summary() -> None:
    router = new_router()
    body = {"notes": 40, "findings": 20, "evidence": 10, "seed": 5}
    first = router.dispatch("performance", "benchmark", body)
    second = router.dispatch("performance", "benchmark", body)
    assert first["digest"] == second["digest"]
    assert first["passed"] is True
    assert len(first["budgets"]) == 7
    assert first["fixture"]["notes"] == 40


def test_flush_route_writes_events() -> None:
    router = new_router()
    payload = router.dispatch(
        "performance",
        "flush",
        {"events": ["alpha", "beta", "gamma"]},
        {"x-request-id": "req_test"},
    )
    assert payload["received"] == 3
    assert payload["flushed"] == 3
    assert payload["checkpoint"] == 3
    assert payload["batches"] == 1
    assert payload["modeled_ms"] > 0


def test_flush_route_validates_input() -> None:
    router = new_router()
    with pytest.raises(V3Error, match="must be a list"):
        router.dispatch("performance", "flush", {"events": "alpha"})
    with pytest.raises(V3Error, match="At most"):
        router.dispatch("performance", "flush", {"events": ["x"] * (MAX_FLUSH_EVENTS + 1)})


def test_benchmark_route_validates_numbers() -> None:
    router = new_router()
    with pytest.raises(V3Error, match="between"):
        router.dispatch("performance", "benchmark", {"notes": -5})
    with pytest.raises(V3Error, match="integer"):
        router.dispatch("performance", "benchmark", {"notes": "not-a-number"})


def test_dynamic_install_registers_performance() -> None:
    router = V3Router()
    installed = router.install_namespaces()
    assert installed >= 2
    assert router.get("performance", "benchmark") is not None
    assert "performance" in router.namespaces()
