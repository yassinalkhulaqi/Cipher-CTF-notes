# Graph Workbench (V3 / B04)

The graph workbench turns the V3 entity graph into an analytical surface: you
can lay it out deterministically, group it, explain a relationship path, find
structural choke points, edit links with undo, capture snapshots, and export
the result — all offline.

This branch reuses the B00 contracts without redefining them:

- `redscribe.v3.entities` — `EntityService`, `LinkGraph`, `EntityId`,
  `EntityLink`, `EntityKindRegistry`.
- `redscribe.v3.events` — `EventBus` and `DomainEvent` for every mutation.
- `redscribe.v3.api` — `V3Router`, envelopes, and stable error codes.
- `redscribe.v3.capabilities` — the `graph` capability gate.

## 1. Package layout

```
src/redscribe/v3/graph_workbench/
├── __init__.py      public facade (all names re-exported)
├── model.py         WorkbenchNode / WorkbenchEdge / WorkbenchGraph
├── layout.py        seeded RNG + four layout strategies + registry
├── clustering.py    tag / kind / severity clustering and chips
├── analysis.py      shortest paths, cut vertices, bridges, components
├── editor.py        reversible relationship commands with undo/redo
├── snapshots.py     bounded snapshot history, digests, and diffs
├── exports.py       DOT / JSON / Mermaid renderers with escaping
└── service.py       GraphWorkbench facade + WorkbenchFilters
src/redscribe/v3/namespaces/graph.py   V3 API namespace (22 routes)
frontend/src/features/graph-workbench/ React feature + CSS
tests/v3_graph_workbench/              Python contract tests
docs/v3/graph-workbench.md             this document
```

## 2. Model

`WorkbenchGraph` is a read-optimized projection of `EntityService.snapshot()`.
Nodes keep the universal `EntityRef`, kind, tags, status, owner, summary,
timestamps, version, and metadata. Severity is derived deterministically from
metadata keys (`severity`, `risk`, `impact`, `priority`, `cvss_severity`,
`cvss`, `score`) and then from `severity/*`, `severity:*`, or `sev/*` tags;
numeric scores map `>=9 → critical`, `>=7 → high`, `>=4 → medium`, `>0 → low`,
and `0 → info`. Unknown values fall back to `unknown`.

Edges wrap `EntityLink` verbatim. Their key is `(source, target, kind)`, so
typed parallel links are preserved. `WorkbenchGraph.validate()` reports self
loops, dangling endpoints, and kind mismatches.

## 3. Layouts

Strategies implement `LayoutStrategy.compute(graph, options) -> LayoutResult`
and register by name in `_LAYOUTS`; `register_layout()` is the additive
extension point.

| Strategy | Behavior |
| --- | --- |
| `force` | Golden-angle seeded initial positions, sampled repulsion, typed-edge attraction, cooling, centering. Iteration budget shrinks for large graphs. |
| `hierarchical` | Directed edge layering from zero in-degree roots (or an explicit root), cycle-safe via visited depth checks; LR/TB direction. |
| `radial` | BFS hop rings around the highest-degree hub (or an explicit root), stable kind ordering within each ring. |
| `timeline` | Sort by `timestamp` or a configured metadata key, one lane per entity kind. |

`SeededRandom` is an xorshift32 generator with a normalized non-zero seed.
All ordering is by stable node id or `blake2b` hash, never Python `hash()` or
wall-clock time. `compute_layout(graph, name, options)` always returns the same
coordinates for the same inputs, which makes snapshots, diffs, and tests
reproducible. Positions are normalized into the padded canvas and rounded to
two decimals.

Example:

```python
from redscribe.v3.graph_workbench import GraphWorkbench, LayoutOptions

layout = workbench.layout("radial", options=LayoutOptions(seed=17, width=1000))
point = layout.point("finding:sql-001")
```

## 4. Clustering

`cluster_graph(graph, dimension)` returns a `ClusterResult` with clusters,
assignments, and unassigned ids. Each node has one primary cluster per
dimension: first sorted tag (namespaced tags such as `severity:high` are
excluded unless a prefix is supplied), entity kind, or normalized severity.
Clusters are size-ordered, colors come from a fixed palette, and chip labels
use the `EntityKindRegistry` (`finding` → "Findings"). `filter_by_cluster()`
returns the induced subgraph; `cluster_centroids()` projects clusters onto a
layout for minimap overlays.

## 5. Analysis

- `shortest_path()` is a deterministic Dijkstra traversal over the undirected
  graph by default. Ties break by node key; weighted mode uses `1 / weight` as
  hop cost; `directed` and `max_hops` are supported. Every hop becomes a
  `PathStep` with a sentence such as
  `Step 1: Root note points to SQL finding via evidences (weight 1.00)`.
- `articulation_points()` uses an iterative Tarjan low-link traversal (no
  recursion limit) and then computes the fragments created by removing each
  cut vertex. Severity rises with the number of fragments.
- `bridges()` reuses the same low-link state to find relationship cut edges.
- `connected_components()`, `neighborhood()`, and `structural_summary()`
  complete the analyst toolkit.

## 6. Relationship editor

`RelationshipEditor` wraps the shared `LinkGraph` and records reversible
commands (`add`, `remove`, `update`) with sequence, actor, timestamp, and
inverse link. `connect`, `disconnect`, `relabel`, `reweight`, `undo`, and
`redo` all validate endpoints through `EntityService` and emit
`graph.link.*` events. History is bounded (default 100 records); clearing
history never mutates the graph. Editing requires the `graph` capability.

## 7. Snapshots and diffs

`SnapshotStore` keeps a bounded (default 16) deque of `GraphSnapshot`
records. Each snapshot carries a SHA-256 digest of a canonical node/edge
payload, a fixed-clock-friendly ISO timestamp, and record counts. Snapshots
round-trip through `as_dict(include_records=True)` /
`GraphSnapshot.from_dict()`. `diff_snapshots()` reports added, removed, and
changed nodes and edges; identical graphs produce `changed: false`.

## 8. Export

| Format | Output |
| --- | --- |
| `dot` | Directed Graphviz graph with semantic colors, optional cluster subgraphs, and highlighted nodes. All labels are quote/newline escaped. |
| `json` | Stable, key-sorted document with generator version and full graph records. |
| `mermaid` | `flowchart` with per-kind `classDef` rules, cluster subgraphs, and HTML-escaped labels. |

Exporters are pure string builders — no subprocesses, no network, no external
assets. `export_graph()` dispatches on `ExportFormat`.

## 9. API namespace

`register(router)` in `redscribe.v3.namespaces.graph` adds 22 routes via
`router.add("graph", action, handler)`. Discovery is automatic; no central
dispatch table is edited.

| Action | Purpose |
| --- | --- |
| `overview`, `graph`, `entities`, `inspect`, `tag-index` | Read graph and universal entity metadata. |
| `layout`, `clusters`, `cluster-dashboard`, `path`, `articulation`, `neighbors` | Analytics. |
| `connect`, `disconnect`, `update-relationship`, `undo`, `redo`, `history` | Undoable editing. |
| `snapshot`, `snapshots`, `diff`, `restore` | Snapshot workflow. |
| `export` | DOT / JSON / Mermaid export. |

Validation failures map to stable V3 codes: `missing_field`,
`invalid_request`, `forbidden`, `not_found`. An `X-Capability` header is
honored; non-graph capabilities are rejected. Tests inject a service with
`set_workbench()`.

## 10. Frontend

`frontend/src/features/graph-workbench/` contains pure modules (`layout`,
`geometry`, `clusters`, `analysis`, `editor`, `minimap`, `inspector`, `client`)
and presentational components:

- `LayoutSwitcher` — four strategies with aria-pressed state.
- `ClusterChips` — dimension switch and colored, toggleable chips.
- `PathExplorer` — endpoint selects, path summary, and step explanations.
- `RelationshipPanel` — source → target gesture, kind/label/weight, connect,
  undo, redo, snapshot.
- `WorkbenchMinimap` — SVG dot projection with a viewport rectangle and
  click-to-recenter.
- `WorkbenchInspector` — entity metadata, tags, clusters, grouped neighbors,
  and metadata from the universal resolver.

The feature uses V3 semantic tokens only, provides `data-*` hooks and ARIA
labels, supports keyboard activation and reduced motion, and ships its own
`graph-workbench.css`. Hosts import that stylesheet once:

```ts
import "../features/graph-workbench/graph-workbench.css";
```

The typed `GraphWorkbenchClient` calls the namespace through the B00
`V3Client`, so envelopes, request IDs, and typed errors come from the shared
client. The component can also run fully offline from `initialGraph` using the
local deterministic layout and analysis mirrors.

## 11. Tests and performance

Python tests in `tests/v3_graph_workbench/` cover model adaptation, layout
determinism (including a 5,000-node timeline budget under 100 ms), clustering
correctness, path/cut-vertex fixtures, undo/redo, snapshot round-trips, export
validity, and namespace routing. Frontend tests in
`frontend/scripts/graph-workbench-v3.test.ts` cover the mirrored algorithms,
gesture state machine, minimap math, inspector formatting, client calls, and
component markup; the suite is registered in `test-suites/04.json` alongside
the pre-existing entry.

## 12. Exit criteria

Any two entities can be selected, connected with a typed and labeled
relationship, explained step by step, captured, diffed, and exported without
leaving the workbench. Layout coordinates depend only on graph content and the
seed; all mutations are reversible and observable as V3 events.
