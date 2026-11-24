"""Performance namespace routes for the V3 API.

This module is discovered dynamically by ``V3Router.install_namespaces``; no
shared B00 registry is edited. Every route is registered through
``router.add("performance", action, handler)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.entities.types import EntityRef
from redscribe.v3.events.outbox import MemoryOutbox, OutboxWriter
from redscribe.v3.events.types import EventRecord, make_event
from redscribe.v3.performance.batching import EventBatcher
from redscribe.v3.performance.benchmark import (
    report_summary,
    run_benchmark,
)
from redscribe.v3.performance.budgets import BUDGETS
from redscribe.v3.performance.fixtures import fixture_documents, generate_fixture
from redscribe.v3.performance.incremental import IncrementalIndex
from redscribe.v3.performance.models import (
    BenchmarkReport,
    FixtureSpec,
    IndexDelta,
    IndexDocument,
    QuerySpec,
)
from redscribe.v3.performance.queryplan import explain_plans

MAX_FLUSH_EVENTS = 1000
SAMPLE_DOCUMENTS = 500
DEFAULT_SPEC = FixtureSpec()


def default_index_query() -> QuerySpec:
    """Return the default query used by the sample index route."""
    return QuerySpec(tokens=("common", "topic00"), limit=25)


@lru_cache(maxsize=2)
def cached_benchmark(notes: int, findings: int, evidence: int, seed: int) -> BenchmarkReport:
    """Run and cache a benchmark keyed by fixture dimensions."""
    spec = FixtureSpec(notes=notes, findings=findings, evidence=evidence, seed=seed)
    return run_benchmark(spec, enforce=False)


@lru_cache(maxsize=4)
def sample_index(notes: int, seed: int) -> dict[str, Any]:
    """Build a small index used by lightweight stats and plan routes."""
    fixture = generate_fixture(FixtureSpec(notes=max(notes, SAMPLE_DOCUMENTS), seed=seed))
    tokens = fixture_documents(fixture)
    documents: list[IndexDocument] = []
    for record, (key, document_tokens) in zip(fixture.notes, tokens, strict=False):
        if key != str(record.entity_id):
            break
        documents.append(
            IndexDocument(
                ref=EntityRef(record.entity_id, record.title),
                text=record.summary,
                tokens=document_tokens,
            )
        )
        if len(documents) >= SAMPLE_DOCUMENTS:
            break
    index = IncrementalIndex()
    index.apply(IndexDelta(upserts=tuple(documents)))
    index.query(default_index_query())
    stats = index.stats()
    stats["plan"] = index.last_plan.as_dict() if index.last_plan else {}
    return stats


def _int_field(
    payload: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int = 20_000,
) -> int:
    """Read a bounded integer field from a request body."""
    raw = payload.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be an integer", field=key)
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be an integer", field=key) from error
    if value < minimum or value > maximum:
        raise V3Error(
            V3ErrorCode.INVALID_REQUEST,
            f"'{key}' must be between {minimum} and {maximum}",
            field=key,
        )
    return value


def register(router: V3Router) -> None:
    """Register all performance routes on the supplied router."""

    def benchmark(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        spec = FixtureSpec(
            notes=_int_field(body, "notes", DEFAULT_SPEC.notes, maximum=50_000),
            findings=_int_field(body, "findings", DEFAULT_SPEC.findings, maximum=50_000),
            evidence=_int_field(body, "evidence", DEFAULT_SPEC.evidence, maximum=50_000),
            seed=_int_field(body, "seed", DEFAULT_SPEC.seed, maximum=1_000_000),
        )
        report = cached_benchmark(spec.notes, spec.findings, spec.evidence, spec.seed)
        summary = report_summary(report)
        summary["plans"] = {name: plan.as_dict() for name, plan in sorted(report.plans.items())}
        return summary

    def budgets(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "budgets": [
                {
                    "name": budget.name,
                    "limit_ms": budget.limit_ms,
                    "metric": budget.metric,
                    "description": budget.description,
                }
                for budget in BUDGETS
            ]
        }

    def fixture(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        spec = FixtureSpec(
            notes=_int_field(body, "notes", 100, maximum=2000),
            findings=_int_field(body, "findings", 50, maximum=2000),
            evidence=_int_field(body, "evidence", 25, maximum=2000),
            seed=_int_field(body, "seed", DEFAULT_SPEC.seed, maximum=1_000_000),
        )
        return generate_fixture(spec).as_dict()

    def index_stats(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        notes = _int_field(body, "notes", SAMPLE_DOCUMENTS, maximum=2000)
        seed = _int_field(body, "seed", DEFAULT_SPEC.seed, maximum=1_000_000)
        return sample_index(notes, seed)

    def plan(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        notes = _int_field(body, "notes", DEFAULT_SPEC.notes, maximum=50_000)
        findings = _int_field(body, "findings", DEFAULT_SPEC.findings, maximum=50_000)
        evidence = _int_field(body, "evidence", DEFAULT_SPEC.evidence, maximum=50_000)
        seed = _int_field(body, "seed", DEFAULT_SPEC.seed, maximum=1_000_000)
        report = cached_benchmark(notes, findings, evidence, seed)
        return {"explain": list(explain_plans(report.plans))}

    def flush(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        raw_events = body.get("events", ())
        if not isinstance(raw_events, (list, tuple)):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'events' must be a list", field="events")
        if len(raw_events) > MAX_FLUSH_EVENTS:
            raise V3Error(
                V3ErrorCode.INVALID_REQUEST,
                f"At most {MAX_FLUSH_EVENTS} events can be flushed per call",
                field="events",
            )
        records: list[EventRecord] = []
        for position, raw in enumerate(raw_events):
            label = raw if isinstance(raw, str) else str(raw)
            records.append(
                EventRecord(
                    sequence=position + 1,
                    event=make_event("performance.flush", label=label[:120]),
                    timestamp=float(position),
                    request_id=headers.get("x-request-id", ""),
                )
            )
        batcher = EventBatcher.with_fixed_clock(OutboxWriter(MemoryOutbox()))
        for record in records:
            batcher.append(record, now=0.0)
        report = batcher.drain()
        result = report.as_dict()
        result["modeled_ms"] = batcher.meter.modeled_ms
        return result

    router.add("performance", "benchmark", benchmark)
    router.add("performance", "budgets", budgets)
    router.add("performance", "fixture", fixture)
    router.add("performance", "index_stats", index_stats)
    router.add("performance", "plan", plan)
    router.add("performance", "flush", flush)


__all__ = ["MAX_FLUSH_EVENTS", "cached_benchmark", "register", "sample_index"]
