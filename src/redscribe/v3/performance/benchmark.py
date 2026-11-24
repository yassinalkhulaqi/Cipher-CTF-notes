"""Reproducible benchmark harness and budget gate for large vaults.

The harness generates fixtures in memory, runs a fixed sequence of scenarios,
and produces a report whose deterministic digest is stable across machines.
Wall-clock timings are recorded for humans but are deliberately excluded from
the digest and from budget assertions.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.events.outbox import MemoryOutbox, OutboxWriter
from redscribe.v3.performance.batching import EventBatcher
from redscribe.v3.performance.budgets import (
    assert_budgets,
    evaluate_budgets,
    format_budgets,
)
from redscribe.v3.performance.fixtures import fixture_documents, generate_fixture
from redscribe.v3.performance.incremental import IncrementalIndex
from redscribe.v3.performance.meter import Meter
from redscribe.v3.performance.models import (
    BenchmarkReport,
    FixtureSpec,
    IndexDelta,
    IndexDocument,
    Measurement,
    QueryPlan,
    QuerySpec,
    VaultFixture,
)
from redscribe.v3.performance.workers import chunk, visible_range

STARTUP_ROWS = 50
INDEX_CHUNK_SIZE = 2000
TREE_SCROLL_TOP = 9600.0
TREE_VIEWPORT_HEIGHT = 720.0
TREE_ROW_HEIGHT = 32.0
TREE_OVERSCAN = 4
EDIT_BATCH_SIZE = 25
FLUSH_BATCH_SIZE = 128
GRAPH_CHUNK_SIZE = 24
GRAPH_SAMPLE_SIZE = 6000

SCENARIO_NAMES: tuple[str, ...] = (
    "startup",
    "index_build",
    "tree_interaction",
    "first_search",
    "cached_search",
    "incremental_edit",
    "event_flush",
    "graph_deferred",
)


def capture(meter: Meter) -> dict[str, int]:
    """Capture a meter snapshot for later delta measurement."""
    return meter.as_dict()


def measurement_from_meter(
    name: str,
    meter: Meter,
    *,
    wall_ms: float = 0.0,
    detail: str = "",
) -> Measurement:
    """Build a measurement from a dedicated meter."""
    return Measurement(
        scenario=name,
        modeled_ms=meter.modeled_ms,
        operations=meter.as_dict(),
        wall_ms=wall_ms,
        detail=detail,
    )


def measurement_from_delta(
    name: str,
    meter: Meter,
    before: dict[str, int],
    *,
    wall_ms: float = 0.0,
    detail: str = "",
) -> Measurement:
    """Build a measurement from the operations added since a snapshot."""
    operations = {
        operation: count - before.get(operation, 0)
        for operation, count in meter.as_dict().items()
        if count - before.get(operation, 0) > 0
    }
    total_us = sum(operations[operation] * meter.costs[operation] for operation in operations)
    return Measurement(
        scenario=name,
        modeled_ms=round(total_us / 1000.0, 4),
        operations=operations,
        wall_ms=wall_ms,
        detail=detail,
    )


def _documents(
    fixture: VaultFixture, tokens: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[IndexDocument, ...]:
    """Pair fixture records with precomputed tokens as index documents."""
    result: list[IndexDocument] = []
    for record, (key, document_tokens) in zip(fixture.notes, tokens, strict=False):
        if key != str(record.entity_id):
            raise ValueError("Fixture token stream is out of sync")
        result.append(
            IndexDocument(
                ref=EntityRef(record.entity_id, record.title),
                text=record.summary,
                tokens=document_tokens,
            )
        )
    return tuple(result)


def _query_tokens(
    fixture: VaultFixture, tokens: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[str, ...]:
    """Choose a deterministic query from the generated notes."""
    if not tokens:
        return ("common",)
    primary = tokens[0][1]
    if not primary:
        return ("common",)
    return (primary[0], primary[-1])


def _startup_measurement(
    fixture: VaultFixture, tokens: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[Measurement, QuerySpec, QueryPlan | None]:
    """Measure a bounded startup load and first window query."""
    meter = Meter()
    index = IncrementalIndex(meter=meter)
    documents = _documents(fixture, tokens)[:STARTUP_ROWS]
    index.apply(IndexDelta(upserts=documents))
    spec = QuerySpec(tokens=_query_tokens(fixture, tokens), limit=STARTUP_ROWS)
    started = perf_counter()
    result = index.query(spec)
    wall_ms = (perf_counter() - started) * 1000.0
    detail = f"rows={len(result.refs)} generation={index.generation}"
    return (
        measurement_from_meter("startup", meter, wall_ms=wall_ms, detail=detail),
        spec,
        result.plan,
    )


def _index_build_measurement(
    fixture: VaultFixture, tokens: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[IncrementalIndex, Measurement]:
    """Build the full index in generations without a single full-vault scan."""
    meter = Meter()
    index = IncrementalIndex(meter=meter)
    documents = _documents(fixture, tokens)
    started = perf_counter()
    for batch in chunk(documents, INDEX_CHUNK_SIZE):
        index.apply(IndexDelta(upserts=batch))
    wall_ms = (perf_counter() - started) * 1000.0
    detail = f"documents={index.size} generations={index.generation}"
    return index, measurement_from_meter("index_build", meter, wall_ms=wall_ms, detail=detail)


def _tree_measurement(fixture: VaultFixture) -> Measurement:
    """Measure the work needed for one virtualized tree interaction."""
    meter = Meter()
    started = perf_counter()
    meter.record("fingerprint_step")
    max_scroll = max(0, len(fixture.notes) - 1) * TREE_ROW_HEIGHT
    start, end = visible_range(
        len(fixture.notes),
        min(TREE_SCROLL_TOP, max_scroll),
        TREE_VIEWPORT_HEIGHT,
        TREE_ROW_HEIGHT,
        TREE_OVERSCAN,
    )
    rows = fixture.notes[start:end]
    meter.record("layout_node", len(rows))
    meter.record("row_materialize", len(rows))
    wall_ms = (perf_counter() - started) * 1000.0
    return measurement_from_meter(
        "tree_interaction",
        meter,
        wall_ms=wall_ms,
        detail=f"window={start}:{end} rendered={len(rows)}",
    )


def _search_measurements(
    index: IncrementalIndex, spec: QuerySpec
) -> tuple[dict[str, Measurement], QueryPlan | None]:
    """Measure a cold and a warm query against the same index."""
    results: dict[str, Measurement] = {}
    first_plan: QueryPlan | None = None
    for name in ("first_search", "cached_search"):
        before = capture(index.meter)
        started = perf_counter()
        result = index.query(spec)
        wall_ms = (perf_counter() - started) * 1000.0
        if name == "first_search":
            first_plan = result.plan
        results[name] = measurement_from_delta(
            name,
            index.meter,
            before,
            wall_ms=wall_ms,
            detail=f"candidates={result.candidates} hits={len(result.refs)} "
            f"cache={'hit' if result.cache_hit else 'miss'}",
        )
    return results, first_plan


def _edit_measurement(index: IncrementalIndex) -> Measurement:
    """Apply a small mutation batch and verify incremental posting updates."""
    edits: list[IndexDocument] = []
    for document in index.documents()[:EDIT_BATCH_SIZE]:
        replacement = ("edited", *tuple(token for token in document.tokens if token != "edited"))
        edits.append(
            IndexDocument(
                ref=EntityRef(document.ref.entity_id, f"{document.ref.label} (edited)"),
                text=document.text,
                tokens=replacement[: len(document.tokens)],
                version=document.version + 1,
            )
        )
    before = capture(index.meter)
    started = perf_counter()
    generation = index.apply(IndexDelta(upserts=tuple(edits)))
    verified = all(document.key in index.postings_for("edited") for document in edits)
    wall_ms = (perf_counter() - started) * 1000.0
    if not verified:
        raise AssertionError("Incremental edit did not update postings")
    return measurement_from_delta(
        "incremental_edit",
        index.meter,
        before,
        wall_ms=wall_ms,
        detail=f"edits={len(edits)} generation={generation}",
    )


def _flush_measurement(fixture: VaultFixture) -> Measurement:
    """Measure deterministic batched writes through the V3 outbox."""
    sink = OutboxWriter(MemoryOutbox())
    batcher = EventBatcher.with_fixed_clock(sink)
    meter = batcher.meter
    records = fixture.events[:2000]
    started = perf_counter()
    for position, record in enumerate(records):
        batcher.append(record, now=float(position) * 0.01)
    report = batcher.drain()
    wall_ms = (perf_counter() - started) * 1000.0
    return measurement_from_meter(
        "event_flush",
        meter,
        wall_ms=wall_ms,
        detail=f"events={report.flushed} batches={report.batches} checkpoint={report.checkpoint}",
    )


def _graph_measurement(fixture: VaultFixture) -> Measurement:
    """Measure one deferred graph projection chunk."""
    meter = Meter()
    node_ids = [str(record.entity_id) for record in fixture.notes[:GRAPH_SAMPLE_SIZE]]
    node_ids.extend(str(record.entity_id) for record in fixture.findings[:GRAPH_SAMPLE_SIZE])
    node_ids.extend(str(record.entity_id) for record in fixture.evidence[:GRAPH_SAMPLE_SIZE])
    started = perf_counter()
    chunks = chunk(tuple(node_ids), GRAPH_CHUNK_SIZE)
    first_chunk = chunks[0] if chunks else ()
    meter.record("graph_node_project", len(first_chunk))
    meter.record("layout_node", len(first_chunk))
    wall_ms = (perf_counter() - started) * 1000.0
    return measurement_from_meter(
        "graph_deferred",
        meter,
        wall_ms=wall_ms,
        detail=f"nodes={len(node_ids)} chunks={len(chunks)} frame_nodes={len(first_chunk)}",
    )


def run_benchmark(spec: FixtureSpec | None = None, *, enforce: bool = True) -> BenchmarkReport:
    """Run every scenario and optionally enforce the budget gate."""
    settings = spec or FixtureSpec()
    started = perf_counter()
    fixture = generate_fixture(settings)
    tokens = fixture_documents(fixture)

    startup, query_spec, startup_plan = _startup_measurement(fixture, tokens)
    index, index_build = _index_build_measurement(fixture, tokens)
    plan_map: dict[str, QueryPlan] = {}
    if startup_plan is not None:
        plan_map["startup"] = startup_plan
    measurements: dict[str, Measurement] = {
        "startup": startup,
        "index_build": index_build,
        "tree_interaction": _tree_measurement(fixture),
    }
    search_measurements, first_plan = _search_measurements(index, query_spec)
    if first_plan is not None:
        plan_map["first_search"] = first_plan
    measurements.update(search_measurements)
    measurements["incremental_edit"] = _edit_measurement(index)
    measurements["event_flush"] = _flush_measurement(fixture)
    measurements["graph_deferred"] = _graph_measurement(fixture)

    budget_results = evaluate_budgets(measurements)
    if enforce:
        assert_budgets(budget_results)
    wall_ms = (perf_counter() - started) * 1000.0
    return BenchmarkReport(
        fixture=fixture,
        measurements=measurements,
        budgets=budget_results,
        plans=plan_map,
        wall_ms=wall_ms,
    )


def render_report(report: BenchmarkReport) -> tuple[str, ...]:
    """Render a benchmark report as stable, documented text lines."""
    lines = [
        "RedScribe V3 performance benchmark",
        f"fixture: {report.fixture.as_dict()}",
        f"fingerprint: {report.fixture.fingerprint}",
        f"digest: {report.digest}",
        f"total_wall_ms: {report.wall_ms:.4f}",
        "",
        f"{'scenario':<22} {'modeled_ms':>12} {'wall_ms':>12}  detail",
    ]
    for name in sorted(report.measurements):
        measurement = report.measurements[name]
        lines.append(
            f"{name:<22} {measurement.modeled_ms:>12.4f} {measurement.wall_ms:>12.4f}  "
            f"{measurement.detail}"
        )
    lines.append("")
    lines.extend(format_budgets(report.budgets))
    lines.append(f"status: {'PASS' if report.passed else 'FAIL'}")
    return tuple(lines)


def report_lines_as_text(lines: tuple[str, ...]) -> str:
    """Join rendered report lines for docs or CLI output."""
    return "\n".join(lines) + "\n"


def report_operations(report: BenchmarkReport) -> dict[str, int]:
    """Aggregate operation counts across all scenarios."""
    totals: dict[str, int] = {}
    for measurement in report.measurements.values():
        for operation, count in measurement.operations.items():
            totals[operation] = totals.get(operation, 0) + count
    return dict(sorted(totals.items()))


def report_summary(report: BenchmarkReport) -> dict[str, Any]:
    """Return a compact summary used by the namespace route."""
    return {
        "digest": report.digest,
        "passed": report.passed,
        "wall_ms": round(report.wall_ms, 4),
        "fixture": report.fixture.as_dict(),
        "measurements": {
            name: measurement.as_dict() for name, measurement in sorted(report.measurements.items())
        },
        "budgets": [result.as_dict() for result in report.budgets],
        "operations": report_operations(report),
    }
