"""Value-model behavior for the performance package."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityId, EntityKind, EntityRef
from redscribe.v3.performance.models import (
    Budget,
    BudgetResult,
    FixtureSpec,
    IndexDelta,
    IndexDocument,
    Measurement,
    PlanNode,
    QueryPlan,
    QuerySpec,
    VaultFixture,
)


def document(key: str, *tokens: str) -> IndexDocument:
    entity_id = EntityId(EntityKind.NOTE, key)
    return IndexDocument(
        ref=EntityRef(entity_id, key),
        text=f"text for {key}",
        tokens=tokens,
    )


def test_index_document_properties() -> None:
    item = document("note-1", "alpha", "beta")
    assert item.key == "note:note-1"
    rendered = item.as_dict()
    assert rendered["tokens"] == ["alpha", "beta"]
    assert rendered["characters"] == len(item.text)
    assert rendered["version"] == 1


def test_index_delta_size_and_emptiness() -> None:
    assert IndexDelta().is_empty()
    delta = IndexDelta(upserts=(document("note-1", "a"),), removals=("note:note-2",))
    assert delta.size == 2
    assert not delta.is_empty()


@pytest.mark.parametrize("limit", [0, 501])
def test_query_spec_rejects_bad_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        QuerySpec(tokens=("alpha",), limit=limit)


def test_query_spec_requires_tokens() -> None:
    with pytest.raises(ValueError, match="at least one token"):
        QuerySpec(tokens=())


def test_query_spec_fingerprint_is_order_independent() -> None:
    first = QuerySpec(tokens=("beta", "alpha"), limit=25)
    second = QuerySpec(tokens=("alpha", "beta"), limit=25)
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != QuerySpec(tokens=("alpha",), limit=25).fingerprint
    assert first.fingerprint != QuerySpec(tokens=("alpha", "beta"), limit=24).fingerprint


def test_plan_explain_and_cost() -> None:
    plan = QueryPlan(
        fingerprint="alpha|25|False",
        generation=3,
        nodes=(
            PlanNode("posting_lookup", "tokens=1", rows_in=1, rows_out=1, cost_ms=0.01),
            PlanNode("rank_window", "limit=25", rows_in=100, rows_out=25, cost_ms=0.02),
        ),
    )
    assert plan.total_cost_ms == pytest.approx(0.03)
    lines = plan.explain()
    assert lines[0].startswith("query alpha|25|False generation=3")
    assert any("posting_lookup" in line for line in lines)
    assert any("total modeled cost" in line for line in lines)
    assert plan.as_dict()["nodes"][0]["cost_ms"] == 0.01


def test_measurement_as_dict_is_stable() -> None:
    measurement = Measurement(
        scenario="first_search",
        modeled_ms=1.23456,
        operations={"posting_lookup": 2},
        wall_ms=0.5,
        detail="hits=3",
    )
    rendered = measurement.as_dict()
    assert rendered["scenario"] == "first_search"
    assert rendered["modeled_ms"] == 1.2346
    assert rendered["operations"] == {"posting_lookup": 2}
    assert rendered["detail"] == "hits=3"


def test_budget_validation_and_result_margin() -> None:
    with pytest.raises(ValueError, match="limit"):
        Budget("broken", 0, "ms", "description")
    budget = Budget("tree", 100.0, "modeled_ms", "tree interaction")
    passed = BudgetResult(budget=budget, measured=42.25, passed=True)
    failed = BudgetResult(budget=budget, measured=150.0, passed=False)
    assert passed.margin_ms == 57.75
    assert failed.margin_ms == -50.0
    assert passed.as_dict()["name"] == "tree"
    assert failed.as_dict()["passed"] is False


def test_fixture_spec_validation_and_counts() -> None:
    spec = FixtureSpec(notes=20, findings=10, evidence=5, seed=7)
    assert spec.total_entities == 35
    assert spec.as_dict()["seed"] == 7
    with pytest.raises(ValueError, match="cannot be negative"):
        FixtureSpec(notes=-1)
    with pytest.raises(ValueError, match="tokens_per_note"):
        FixtureSpec(tokens_per_note=0)
    with pytest.raises(ValueError, match="positive"):
        FixtureSpec(event_sample_every=0)


def test_vault_fixture_all_records() -> None:
    spec = FixtureSpec(notes=2, findings=2, evidence=1)
    fixture = VaultFixture(
        spec=spec,
        notes=(document("note-1"), document("note-2")),
        findings=(document("finding-1"), document("finding-2")),
        evidence=(document("evidence-1"),),
        linked=(),
        events=(),
        fingerprint="abc",
    )
    assert len(fixture.all_records()) == 5
    summary = fixture.as_dict()
    assert summary["fingerprint"] == "abc"
    assert summary["notes"] == 2
