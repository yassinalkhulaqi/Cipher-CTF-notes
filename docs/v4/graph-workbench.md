# Graph workbench (v4)

The graph workbench turns typed vault references into a navigable link-analysis
surface. It provides deterministic layouts, composable filters, relationship
legends, named snapshots, and a read-only v4 API. The implementation lives in
`redscribe.v4.graph_v4` and in the frontend feature directory
`src/features/v4/graph-workbench/` (a v4-specific path because the slug collides
with the v3 workbench).

## Goals

- Reuse the shared v4 contracts (`EntityRef`, `EntityLink`, envelopes, events,
  pagination, capabilities) instead of introducing a parallel vocabulary.
- Keep every computation deterministic and data-only: no shell, no evaluation,
  no network calls from the domain layer.
- Give the UI enough typed state to render a canvas, filter rail, legend, and
  inspector without duplicating business rules.

## Domain model

### `types.py`

| Type | Responsibility |
| --- | --- |
| `GraphNode` | A vertex with `id`, `kind`, `label`, and `weight`; converts to/from `EntityRef`. |
| `GraphEdge` | A typed relationship with `source`, `target`, `relation`, and `weight`. |
| `GraphFilter` | Immutable predicates over kinds, relations, minimum weight, and label text. |
| `LayoutKind` | `FORCE`, `CIRCULAR`, or `GRID`, with strict parsing. |
| `GraphMetrics` | Counts, degree map, density, isolated nodes, and component count. |
| `GraphPoint` / `LayoutResult` | Positioned nodes and the dimensions/seed used to produce them. |
| `GraphData` | A validated, sorted pair of node and edge tuples. |
| `FilterResult` | Visible items plus hidden-item accounting. |
| `GraphSnapshot` | A named, timestamped view with a filter, layout, and tags. |

All value types validate their invariants in `__post_init__` and round-trip
through `to_dict` / `from_dict`. Relation slugs follow the shared contract
pattern; weights are finite values in `[0, 1]`; node and snapshot names are
bounded and normalized.

### Filter semantics

A node is hidden when its kind is excluded or its label does not contain the
search text (case-insensitive). An edge is hidden when its relation is excluded,
its weight is below `min_weight`, or either endpoint is hidden. `FilterResult`
reports both hidden counts and the exact hidden ids/keys so the API can explain
what the user no longer sees.

## Services (`service.py`)

- `GraphBuilder` accumulates `EntityRef`s and `EntityLink`s, deduplicates nodes
  by id and edges by `(source, target, relation)`, merges weights by maximum,
  and emits a canonically sorted `GraphData`.
- `GraphAnalyzer` provides undirected degree centrality, connected components,
  BFS shortest paths, isolated nodes, neighbour lookup, ego networks, relation
  statistics, diameter, and metrics.
- `ForceLayout` runs a seeded spring simulation for a fixed iteration count.
  Initial coordinates come from SHA-256 hashes of `seed:salt:node_id`, so two
  runs with the same inputs produce byte-identical results. Repulsion, spring
  forces, damping, and clamping keep every point inside the viewport.
- `CircularLayout` and `GridLayout` place sorted nodes deterministically;
  `LayoutEngine` / `compute_layout` dispatch between strategies.
- `FilterEngine` applies a `GraphFilter` and returns a `FilterResult`.

## Storage (`storage.py`)

`GraphStore` works against a `SnapshotRepository` protocol. The default
`InMemoryGraphRepository` is deterministic and process-local;
`SqliteGraphRepository` uses a caller-supplied `sqlite3.Connection` and persists
JSON payloads in two tables. The store validates names, rejects conflicting
writes, and supports save/load/delete, a named filter index, clone, and JSON
export/import.

## HTTP surface (`api.py`)

All routes return v4 envelopes (`{"data": ..., "meta": ...}`) or structured
errors. `GraphRequest` parses and validates query parameters into typed values
before any handler runs. Every request validates common parameters, so invalid
pagination or filter values produce `invalid_input` regardless of route.

| Route | Purpose |
| --- | --- |
| `/api/v4/graph` | Overview: counts, legend, density, hidden counts, current filter. |
| `/api/v4/graph/nodes` | Paginated visible nodes. |
| `/api/v4/graph/edges` | Paginated visible edges. |
| `/api/v4/graph/metrics` | Metrics for the filtered graph. |
| `/api/v4/graph/layout` | Deterministic coordinates for a requested layout. |
| `/api/v4/graph/path` | BFS shortest path between two node ids. |
| `/api/v4/graph/filters` | Facets, saved filters, and hidden node ids. |
| `/api/v4/graph/snapshots` | Paginated snapshot names. |
| `/api/v4/graph/snapshot` | One named snapshot. |
| `/api/v4/graph/export` | JSON export of a snapshot or the current view. |

Handlers call `FeatureGate.require(GRAPH_WORKBENCH)` and
`CapabilitySet.require(READ)`; export additionally requires `EXPORT`.
`GRAPH_FILTERED` events are published through the shared `EventBus` with a
redacted outbox payload describing the source, filter, and visible/hidden
counts.

## Frontend

- `client.ts` wraps `V4Client` with typed DTOs, a sorted query encoder, and one
  method per route.
- `state.ts` holds the reducer, filter state, visibility helpers, legend
  aggregation, neighbour/inspector helpers, and client-side metrics.
- `GraphCanvas.tsx` renders a header with layout switcher, metrics strip, a
  filter rail, an SVG canvas with clickable nodes and weighted edges, a node
  inspector, and a relationship legend.
- `graph-workbench.css` imports the v4 token stylesheet and uses only
  `var(--v4-*)` tokens, with responsive and reduced-motion rules.

The reducer is deliberately independent of React so it can be exercised by the
`node:test` suite. Tests cover filter immutability, visibility semantics,
metrics, query encoding, and API envelope/error decoding.

## Invariants and limits

- Node ids match a bounded slug/UUID pattern; edges cannot be self-loops.
- Snapshot tags are capped at eight, filter text at 120 characters, and API
  pagination at 200 items per page.
- Layouts clamp coordinates to the requested viewport; force iteration count is
  capped at 200 by the API.
- No route mutates a graph: snapshots are written only through `GraphStore`, and
  handlers never execute supplied code.
