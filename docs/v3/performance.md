# RedScribe V3 — Performance and Scale (B11)

## 1. Intent

B11 proves and enforces performance at realistic research scale. It adds an
incremental index, batched event flushing, query-plan instrumentation, pure
worker-friendly helpers, deterministic in-memory fixtures, a benchmark harness,
and hard budget assertions. The React feature adds virtualized tree/table/list
primitives, skeleton states, a performance HUD, and deferred graph rendering.

No runtime dependencies were added. No network or shell execution is performed.
Benchmark fixtures are generated in memory and never written to disk.

## 2. Contracts reused from B00

B11 does not redefine shared contracts. It imports and uses:

- `EntityId`, `EntityKind`, `EntityRef`, `EntityRecord` from
  `redscribe.v3.entities.types`.
- `DomainEvent`, `EventRecord`, `make_event` from `redscribe.v3.events.types`.
- `EventBus` from `redscribe.v3.events.bus` (fixture event generation).
- `OutboxWriter`, `MemoryOutbox` from `redscribe.v3.events.outbox` (batch sink).
- `FixedClock`, `epoch_start` from `redscribe.v3.clock`.
- `V3Router` and `V3Error` from `redscribe.v3.api` (namespace registration).
- Dynamic namespace discovery: `namespaces/performance.py` is picked up by
  `pkgutil.iter_modules`; no shared registry file is edited.
- `V3Panel` and `V3Stat` from `frontend/src/v3/components/V3Panel.tsx`.

## 3. Backend layout

| Module | Responsibility |
| --- | --- |
| `models.py` | Index documents/deltas, query specs/results, plans, measurements, budgets, fixtures, reports |
| `meter.py` | Deterministic microsecond cost model and operation counters |
| `workers.py` | Pure tokenization, posting construction/merge/delta, scoring, ranking, chunking, windowing |
| `incremental.py` | `IncrementalIndex`: generation tracking and token-scoped cache invalidation |
| `batching.py` | `EventBatcher`: size/byte/time flush triggers, dedupe, checkpoint reporting |
| `queryplan.py` | `PlanRecorder` and plan comparison/explanation helpers |
| `fixtures.py` | Reproducible in-memory 20k/10k/5k fixture generator |
| `budgets.py` | Budget rules, evaluation, formatting, and `BudgetError` |
| `benchmark.py` | Scenario runner, report rendering, summaries, digest |
| `namespaces/performance.py` | Six V3 routes: benchmark, budgets, fixture, index_stats, plan, flush |

### 3.1 Incremental index

Mutations are applied through `IndexDelta`. Each batch increments a generation,
updates only the affected posting lists, and evicts only cache entries whose
query tokens intersect the touched token set. An unrelated edit therefore keeps
a cached result warm, while a related edit invalidates it. `is_consistent()`
compares incremental postings with a full rebuild and is used by tests.

### 3.2 Batched event flush

`EventBatcher` writes through any `write_many`/`checkpoint` sink; `OutboxWriter`
satisfies it. Triggers are injectable (`max_size`, `max_bytes`, `max_lag`), and
timestamps are supplied explicitly, so flush behavior is deterministic.
Duplicate sequence numbers are dropped and reported.

### 3.3 Query-plan instrumentation

Every index query records `cache_lookup`, `posting_lookup`, `posting_union`,
`candidate_score`, and `rank_window` nodes (or `cache_hit`). Nodes carry row
counts and modeled cost, and `explain()` renders a stable trace. Plans are
exposed through `/api/v3/performance/plan`.

### 3.4 Reproducibility and cost model

Wall-clock time varies with runner I/O, so CI budgets assert against a
deterministic modeled cost: recorded operation counts multiplied by a fixed
microsecond cost per operation. Wall time is still measured and reported for
humans, but is excluded from the report digest and from pass/fail decisions.
The digest covers the fixture fingerprint plus every scenario's modeled cost
and operation counts. Repeated runs of the same spec produce the same digest.

## 4. Measured results

Command used (baseline commit `c65e699`, branch `dev/v3-11-performance-scale`):

```bash
PYTHONPATH=src python3 - <<'PY'
import sys
from redscribe.v3.performance import FixtureSpec, render_report, report_lines_as_text, run_benchmark
sys.stdout.write(report_lines_as_text(render_report(run_benchmark(FixtureSpec()))))
PY
```

Fixture: 20,000 notes / 10,000 findings / 5,000 evidence = 35,000 entities,
15,000 links, 2,500 events, seed 11, 6 tokens per note.
Fingerprint `08b497bb845eef3f28eb054f`, report digest
`5aead08fe66cd02dcda1514f`.

| Scenario | Modeled ms | Wall ms (observed) | Detail |
| --- | ---: | ---: | --- |
| startup | 0.0866 | 0.1093 | 7 rows materialized, generation 1 |
| index_build | 22.0000 | 212.5320 | 20,000 documents in 10 generations |
| tree_interaction | 0.3104 | 0.0156 | window 296:327, 31 rows rendered |
| first_search | 5.1776 | 41.2851 | 2,307 candidates, 50 hits, cache miss |
| cached_search | 0.1003 | 0.0287 | same query, cache hit |
| incremental_edit | 0.0275 | 27.1736 | 25 edits, generation 11, no rebuild |
| event_flush | 2.4000 | 83.6293 | 2,000 events in 20 batches |
| graph_deferred | 0.2184 | 2.4703 | 17,000 nodes, 709 chunks, 24 nodes/frame |

Wall numbers are from one run on the development host and are informational;
the modeled numbers are reproducible.

## 5. Budget assertions

| Budget | Limit | Measured | Status | Meaning |
| --- | ---: | ---: | --- | --- |
| tree_interaction | 100 ms | 0.3104 ms | PASS | Expand/scroll a node in a 20k-note tree |
| first_search | 150 ms | 5.1776 ms | PASS | First bounded result window from a cold query |
| startup_load | 250 ms | 0.0866 ms | PASS | Initial bounded index window |
| startup_rows | 50 rows | 7 rows | PASS | No full-vault load on startup |
| incremental_edit | 50 ms | 0.0275 ms | PASS | 25-document mutation batch |
| event_flush | 200 ms | 2.4000 ms | PASS | Flush 2,000 generated events |
| graph_deferred_frame | 16 ms | 0.2184 ms | PASS | One projection chunk fits a 60 fps frame |

`assert_budgets()` raises `BudgetError` with the failing list; `run_benchmark()`
enforces by default and the namespace route reports `passed` instead of
throwing. Budget failure coverage is tested by raising a modeled operation cost
in a test and asserting the gate trips.

## 6. Frontend interaction budgets

The feature lives in `frontend/src/features/performance/`:

| Primitive | File | Budget |
| --- | --- | --- |
| Virtualized tree | `TreeVirtualizer.tsx` | 31 of 20,000 rows in DOM |
| Virtualized table | `TableVirtualizer.tsx` | fixed 32 px rows, overscan 4 |
| Virtualized list | `ListVirtualizer.tsx` | reports live rendered/total ratio |
| Skeleton states | `Skeletons.tsx` | `aria-busy`, stable shimmer, reduced-motion off switch |
| Performance HUD | `PerformanceHUD.tsx` | frame avg/p95, index freshness, budget bars |
| Deferred graph | `DeferredGraph.tsx` | 24 nodes per idle chunk, yields between chunks |

Pure helpers (`virtual.ts`, `frameMonitor.ts`, `freshness.ts`,
`deferredGraph.ts`) are independently tested by
`frontend/scripts/performance-v3.test.ts` registered through
`frontend/scripts/test-suites/11.json`. No shared frontend test list was
edited. Styling is isolated in `performance.css` and imported only by the
feature index.

Interaction rules documented for designers:

- Never render more than one viewport plus four rows of overscan.
- Keep per-frame graph work at or below 12 modeled units (~16 ms budget).
- Show skeletons instead of blank containers while data is loading.
- Keep freshness and budget status visible in the HUD during long operations.

## 7. Exit criteria

| Master-plan criterion | Evidence |
| --- | --- |
| Tree interaction < 100 ms | modeled 0.3104 ms (budget PASS) |
| First search results < 150 ms | modeled 5.1776 ms (budget PASS) |
| No full-vault load on startup | 7 rows materialized; budget `startup_rows` <= 50 |
| Benchmark reproducibility | stable digest, covered by `test_benchmark_is_reproducible` |
| Index consistency under concurrent edits | `is_consistent()` tests in `test_incremental.py` |
| Virtualized list correctness | `computeWindow`, `sliceWindow`, `flattenTree` frontend tests |
| Budget failures in CI | `assert_budgets` and `BudgetError` tests |
| Measured numbers in docs | this section |

## 8. API surface

| Route | Body | Result |
| --- | --- | --- |
| `/api/v3/performance/benchmark` | optional `notes`, `findings`, `evidence`, `seed` | report summary, digest, budgets, plans |
| `/api/v3/performance/budgets` | – | budget definitions |
| `/api/v3/performance/fixture` | bounded fixture dimensions | fixture summary (no records) |
| `/api/v3/performance/index_stats` | optional `notes`, `seed` | sample index stats and plan |
| `/api/v3/performance/plan` | optional fixture dimensions | explained plan lines |
| `/api/v3/performance/flush` | `events` list (<= 1000) | flush report and modeled cost |

All routes are registered through `router.add("performance", action, handler)`
and return plain dictionaries suitable for the B00 envelope layer.
