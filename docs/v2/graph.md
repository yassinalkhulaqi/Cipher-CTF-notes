# V2 Graph Intelligence

The V2 graph-intelligence package turns vault notes, folders, wikilinks, tags, and unresolved references into a typed graph. It exposes extraction, storage, analysis, recommendations, snapshots, and a V2 API namespace. The React feature under `frontend/src/features/graph` consumes the same payloads.

## Scope

- New backend package: `src/redscribe/v2/graph/`.
- New API namespace: `src/redscribe/ui/web/v2/namespaces/graph.py`.
- New frontend feature: `frontend/src/features/graph/`.
- New tests: `tests/v2_graph/` and `frontend/scripts/graph.test.ts`.
- No shared kernel files are modified.

## Data model

`GraphModel` is the canonical in-memory representation. It holds immutable `GraphNode` and `GraphEdge` records plus dictionaries indexed by node id and edge key.

### Node kinds

| Kind | Meaning |
| --- | --- |
| `note` | A live vault note. |
| `folder` | A live vault folder. |
| `reference` | An unresolved wikilink target. |
| `tag` | A tag vertex synthesized from stored, frontmatter, or inline tags. |

### Edge kinds

| Kind | Meaning |
| --- | --- |
| `parent` | Folder containment. |
| `link` | A resolved or unresolved wikilink. |
| `tag` | Note-to-tag membership. |
| `mention` | A non-link mention used by analysis. |

Nodes validate their `kind` and non-negative `weight`; edges validate their `kind` and non-negative `weight`. `GraphModel.validate()` reports dangling edges, self-loops, and mismatched keys.

## Extraction

`extract.py` is conservative and offset-preserving:

- Fenced code and inline code are masked before scanning.
- Escaped wikilinks such as `\\[[Note]]` are ignored.
- Wikilinks support `[[Target]]`, `[[Target|Alias]]`, and `[[Target#Heading|Alias]]`.
- Inline hashtags ignore Markdown headings and code spans.
- Frontmatter tags are read from `tags`, `tag`, or `keywords`.
- Tags are merged case-insensitively in stable first-seen order.
- Duplicate tags prefer frontmatter over inline over stored values.

`normalize_reference()` strips headings, converts backslashes to slashes, and slugifies the target so `[[Corporate#Scope]]` and `corporate` resolve identically.

## Stores

`NodeStore` indexes nodes by id, kind, and case-folded tag. `EdgeStore` indexes outgoing, incoming, and undirected adjacency. `GraphStore` pairs both and can round-trip through `GraphModel`.

`build_graph_store(vault)` creates the store from live vault data:

1. Every live node becomes a note or folder vertex.
2. `parent` edges are created from `parent_id`.
3. Resolved wikilinks become `link` edges.
4. Unresolved wikilinks reuse one synthetic `reference` vertex per normalized target.
5. Tags become synthetic `tag` vertices with `tag` edges.

Synthetic ids are negative: references start at `-1_000_000`, tags at `-2_000_000`.

## Analysis

`algorithms.py` provides deterministic graph analysis:

- `connected_components`: undirected reachability grouped largest-first.
- Centrality: degree, closeness, betweenness, and eigenvector power iteration.
- `clustering_coefficients` and `average_clustering`: triangle-based local clustering.
- `shortest_path`: Dijkstra with optional weights, direction, and hop limits.
- `find_cycles`: canonical simple-cycle discovery via DFS back edges.
- `detect_communities`: deterministic asynchronous label propagation.
- `graph_metrics`: compact dashboard metrics including density and component sizes.

All scores are rounded and ordered deterministically so API responses remain stable.

## Links and recommendations

`LinkService` derives backlinks, outlinks, unresolved references, and snippet text from the graph store plus note bodies. Snippets reuse the extraction offsets so the exact wikilink is highlighted.

`RecommendationService` provides:

- Missing links from unresolved references and two-hop neighborhoods.
- Related notes from tag overlap, shared neighbors, and title similarity.
- Tag-based suggestions for notes in one tag community.
- Popular notes ranked by in-degree.
- A combined `dashboard()` payload.

## Snapshots

`SnapshotStore` keeps a bounded in-memory history of `GraphSnapshot` records. Each snapshot stores metadata plus immutable node and edge tuples. `diff_snapshots()` compares node ids and edge keys, reporting additions and removals. Snapshots support capture, list, get, restore, diff, delete, and capacity pruning.

## Graph intelligence facade

`GraphIntelligenceService` composes all subsystems over a lazily built store. It supports filtering, overview metrics, node/edge listing, bounded neighborhoods, centrality, clustering, components, communities, cycles, paths, label resolution, recommendations, layout payloads, snapshots, and a combined `insights()` dashboard.

`GraphFilters` validates API-style filter dictionaries. It understands `kinds`, `tags`, `statuses`, `query`, and `max_nodes`, and applies them to both vertices and surviving edges.

## V2 API namespace

`register(api)` registers every graph route on an `ApiV2` registry. It is idempotent and binds one service per API instance with a `WeakKeyDictionary`.

### Read routes

| Route | Purpose |
| --- | --- |
| `graph.overview` | Stats, metrics, tags, and snapshot count. |
| `graph.nodes` | Filterable, paginated vertices. |
| `graph.edges` | Filterable, paginated edges. |
| `graph.neighbors` | Bounded neighborhood around one vertex. |
| `graph.backlinks` | Resolved notes linking to one note. |
| `graph.outlinks` | Resolved links and unresolved references from one note. |
| `graph.dangling` | Unresolved wikilinks across the vault. |
| `graph.path` | Shortest path between two vertices or labels. |
| `graph.components` | Connected components. |
| `graph.centrality` | Ranked centrality scores. |
| `graph.clustering` | Local and average clustering. |
| `graph.communities` | Detected communities. |
| `graph.cycles` | Simple cycles. |
| `graph.recommend` | Recommendation dashboard. |
| `graph.related` | Notes related to one note. |
| `graph.tags` | Notes sharing a tag. |
| `graph.resolve` | Resolve a wikilink label to a note id. |
| `graph.layout` | Frontend-ready node and edge payload. |
| `graph.insights` | Combined intelligence dashboard. |

### Snapshot routes

| Route | Purpose |
| --- | --- |
| `graph.snapshot.create` | Capture a named snapshot. |
| `graph.snapshot.list` | List snapshot metadata. |
| `graph.snapshot.get` | Return one snapshot with records. |
| `graph.snapshot.restore` | Return the snapshot's model. |
| `graph.snapshot.diff` | Diff two snapshots. |
| `graph.snapshot.delete` | Delete one snapshot. |

Mutation routes are marked mutating and support idempotency keys through the shared V2 router.

## Frontend feature

The React feature is composed of small pure modules:

- `types.ts`: shared payload and state types.
- `geometry.ts`: vector, distance, and rectangle helpers.
- `layout.ts`: deterministic force, circle, grid, radial, and tree layouts.
- `filters.ts`: query, tag, kind, status, and size filters.
- `clusters.ts`: component, tag, and kind clustering with collapse support.
- `canvas.ts`: viewport transforms, hit testing, LOD, and drawing.
- `inspector.ts`: inspector models, grouping, stats, and navigation.
- `pathAlgorithms.ts`: frontend path finding and path presentation helpers.
- `client.ts`: typed wrapper around `V2Client`.
- `GraphCanvas.tsx`, `NodeInspector.tsx`, `PathExplorer.tsx`, `GraphFeature.tsx`: React UI.

`frontend/src/styles/graph.css` is imported from the global stylesheet.

## Testing

Python tests live in `tests/v2_graph/` and cover the model, extraction, stores, algorithms, service facade, snapshots, and the API namespace. Frontend tests live in `frontend/scripts/graph.test.ts` and cover geometry, layouts, filters, clusters, canvas math, path finding, inspector helpers, and the API client.

Run the relevant suites with:

```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio tests/v2_graph
cd frontend && npm test
```
