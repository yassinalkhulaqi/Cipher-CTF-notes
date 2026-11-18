import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_SCALE,
  MIN_SCALE,
  drawGraph,
  fitViewport,
  hitTestEdge,
  hitTestNode,
  identityViewport,
  lodLevel,
  panViewport,
  screenToWorld,
  shouldDrawLabels,
  worldToScreen,
  zoomAt,
} from "../src/features/graph/canvas";
import {
  buildClusters,
  clusterColor,
  clusterOf,
  clusterSummary,
  connectedGroups,
  spreadClusters,
  visibleNodeIds,
} from "../src/features/graph/clusters";
import { GraphApiClient } from "../src/features/graph/client";
import {
  activeFilterCount,
  degrees,
  edgeKindCounts,
  filterGraph,
  filterNodes,
  normalizeQuery,
  normalizeTags,
  reachableFrom,
  sortByDegree,
  toggleValue,
  withFilterDefaults,
} from "../src/features/graph/filters";
import {
  centroid,
  clamp,
  distance,
  lerp,
  normalize,
  smoothstep,
} from "../src/features/graph/geometry";
import {
  buildInspectorModel,
  breadcrumbs,
  defaultInspectorState,
  formatCount,
  formatScore,
  groupNeighbors,
  inspectorStats,
  nextInspectorSelection,
  selectInspectorNode,
  toggleInspectorSection,
  truncateLabel,
} from "../src/features/graph/inspector";
import {
  createRandom,
  forceLayout,
  gridLayout,
  hashSeed,
  layoutGraph,
  normalizePositions,
  radialLayout,
  treeLayout,
} from "../src/features/graph/layout";
import {
  buildAdjacency,
  depthMap,
  findGraphPath,
  pathEdgeKeys,
  pathKinds,
  pathNodeIds,
  pathSummary,
  pushPathHistory,
  reachableCount,
} from "../src/features/graph/pathAlgorithms";
import type {
  GraphLinkDetail,
  GraphPayload,
  GraphRecommendation,
} from "../src/features/graph/types";
import {
  DEFAULT_FILTERS,
  GRAPH_EDGE_KINDS,
  GRAPH_NODE_KINDS,
} from "../src/features/graph/types";
import { V2Client } from "../src/lib/apiClient";

function samplePayload(): GraphPayload {
  return {
    nodes: [
      {
        id: 1,
        label: "Alpha",
        kind: "note",
        tags: ["crypto"],
        path: "vault/Alpha.md",
      },
      {
        id: 2,
        label: "Beta",
        kind: "note",
        tags: ["crypto", "web"],
        path: "vault/Beta.md",
      },
      {
        id: 3,
        label: "Gamma",
        kind: "note",
        tags: ["web"],
        path: "vault/Gamma.md",
      },
      { id: 4, label: "Delta", kind: "reference", path: "vault/Delta.md" },
      {
        id: 5,
        label: "Pentest",
        kind: "note",
        tags: ["web"],
        path: "vault/Pentest.md",
      },
      {
        id: 6,
        label: "Orphan",
        kind: "note",
        tags: [],
        path: "vault/Orphan.md",
      },
    ],
    edges: [
      { source: 1, target: 2, kind: "link", weight: 1 },
      { source: 2, target: 3, kind: "link", weight: 2 },
      { source: 3, target: 5, kind: "tag", weight: 1 },
      { source: 1, target: 6, kind: "link", weight: 1 },
      { source: 4, target: 1, kind: "mention", resolved: false },
    ],
    stats: { nodes: 6, edges: 5 },
  };
}

test("geometry primitives clamp, normalize, and interpolate points", () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(clamp(-2, 0, 3), 0);
  assert.equal(lerp(0, 10, 0.25), 2.5);
  assert.equal(smoothstep(-1), 0);
  assert.equal(smoothstep(2), 1);
  assert.deepEqual(normalize({ x: 0, y: 0 }), { x: 0, y: 0 });
  const unit = normalize({ x: 3, y: 4 });
  assert.ok(Math.abs(Math.hypot(unit.x, unit.y) - 1) < 1e-9);
  assert.equal(distance({ x: 0, y: 0 }, { x: 3, y: 4 }), 5);
  assert.deepEqual(
    centroid([
      { x: 0, y: 0 },
      { x: 4, y: 2 },
    ]),
    { x: 2, y: 1 },
  );
});

test("layouts produce a deterministic position for every node", () => {
  const payload = samplePayload();
  assert.equal(hashSeed("alpha"), hashSeed("alpha"));
  assert.notEqual(hashSeed("alpha"), hashSeed("beta"));
  const random = createRandom(42);
  const first = random();
  const second = random();
  assert.notEqual(first, second);
  assert.ok(first >= 0 && first < 1);
  for (const kind of ["force", "circle", "grid", "radial", "tree"] as const) {
    const positions = layoutGraph(payload.nodes, payload.edges, kind, {
      iterations: 12,
      width: 800,
      height: 600,
    });
    for (const node of payload.nodes) {
      assert.ok(positions.has(node.id), `${kind} missing ${node.id}`);
    }
  }
  const grid = gridLayout(payload.nodes);
  assert.equal(grid.size, payload.nodes.length);
  assert.deepEqual(gridLayout([]).size, 0);
  assert.ok(radialLayout(payload.nodes, payload.edges).has(1));
  assert.ok(treeLayout(payload.nodes, payload.edges).has(1));
  const forced = forceLayout(payload.nodes, payload.edges, { iterations: 5 });
  assert.ok([...forced.values()].some((point) => Number.isFinite(point.x)));
  const centered = normalizePositions(grid, 800, 600);
  assert.deepEqual(centroid([...centered.values()]), { x: 400, y: 300 });
  assert.equal(normalizePositions(new Map()).size, 0);
});

test("filters normalize tags, apply node filters, and prune dangling edges", () => {
  assert.equal(normalizeQuery("  CRYPTO "), "crypto");
  assert.deepEqual(normalizeTags([" #Web ", "web", "", "crypto"]), [
    "web",
    "crypto",
  ]);
  const filters = withFilterDefaults({
    query: " beta ",
    tags: ["#web"],
    kinds: ["note"],
  });
  assert.deepEqual(filters.tags, ["web"]);
  assert.equal(activeFilterCount(filters), 3);
  assert.deepEqual(
    filterNodes(samplePayload().nodes, filters).map((node) => node.id),
    [2],
  );
  const limited = filterNodes(
    samplePayload().nodes,
    withFilterDefaults({ maxNodes: 2 }),
  );
  assert.equal(limited.length, 2);
  const byKind = filterGraph(
    samplePayload(),
    withFilterDefaults({ kinds: ["reference"] }),
  );
  assert.deepEqual(
    byKind.nodes.map((node) => node.id),
    [4],
  );
  assert.equal(byKind.edges.length, 0);
  const byTag = filterGraph(
    samplePayload(),
    withFilterDefaults({ tags: ["web"] }),
  );
  assert.deepEqual(
    byTag.nodes.map((node) => node.id),
    [2, 3, 5],
  );
  assert.equal(toggleValue(["a", "b"], "a").join(""), "b");
  assert.equal(toggleValue(["a"], "b").join(""), "ab");
  assert.deepEqual(DEFAULT_FILTERS.kinds, []);
});

test("filter helpers compute degree, ordering, reachability, and edge counts", () => {
  const payload = samplePayload();
  const counts = degrees(payload.nodes, payload.edges);
  assert.equal(counts.get(1), 3);
  assert.equal(counts.get(6), 1);
  assert.equal(sortByDegree(payload.nodes, payload.edges)[0].id, 1);
  assert.deepEqual(
    reachableFrom(payload, 3, 1).nodes.map((node) => node.id),
    [2, 3, 5],
  );
  assert.equal(reachableFrom(payload, 1, 0).nodes.length, 1);
  assert.deepEqual(edgeKindCounts(payload.edges), {
    link: 3,
    tag: 1,
    "mention:unresolved": 1,
  });
});

test("clusters group connected nodes and collapse visibility", () => {
  const payload = samplePayload();
  const groups = connectedGroups(payload.nodes, payload.edges);
  assert.equal(groups.length, 1);
  assert.ok(groups[0].includes(1));
  assert.strictEqual(clusterOf([], 1), 0);
  assert.equal(clusterColor(-1), clusterColor(9));
  const clusters = buildClusters(payload, "kind");
  assert.equal(clusters.length, 2);
  assert.equal(visibleNodeIds(clusters).size, 6);
  const collapsed = clusters.map((cluster, index) => ({
    ...cluster,
    collapsed: index === 0,
  }));
  assert.ok(visibleNodeIds(collapsed).size < 6);
  assert.deepEqual(clusterSummary(collapsed), {
    total: 2,
    collapsed: 1,
    nodes: 6,
    largest: 5,
  });
  const positions = layoutGraph(payload.nodes, payload.edges, "grid");
  const spread = spreadClusters(clusters, positions, 50);
  assert.equal(spread.size, positions.size);
});

test("canvas transform, hit testing, and level of detail helpers", () => {
  const viewport = { x: 20, y: -10, scale: 1.5 };
  const point = { x: 4, y: 6 };
  assert.deepEqual(
    screenToWorld(worldToScreen(point, viewport), viewport),
    point,
  );
  assert.deepEqual(worldToScreen(point, identityViewport()), point);
  const zoomed = zoomAt(viewport, 2, { x: 100, y: 100 });
  assert.equal(zoomed.scale, 3);
  assert.equal(zoomAt(viewport, 0.00001, { x: 0, y: 0 }).scale, MIN_SCALE);
  assert.equal(zoomAt(viewport, 1000, { x: 0, y: 0 }).scale, MAX_SCALE);
  assert.deepEqual(panViewport(viewport, 5, -5), { x: 25, y: -15, scale: 1.5 });
  const fitted = fitViewport(
    new Map([
      [1, { x: 10, y: 20 }],
      [2, { x: 30, y: 40 }],
    ]),
    { width: 100, height: 100 },
    0,
  );
  assert.ok(fitted.scale > 0);
  assert.equal(fitViewport(new Map(), { width: 100, height: 100 }).scale, 1);
  assert.equal(lodLevel(0.2), "low");
  assert.equal(lodLevel(0.8), "medium");
  assert.equal(lodLevel(2), "high");
  assert.equal(shouldDrawLabels(0.5), false);
  assert.equal(shouldDrawLabels(0.8), true);

  const positions = new Map([
    [1, { x: 0, y: 0 }],
    [2, { x: 100, y: 0 }],
  ]);
  const nodes = samplePayload().nodes;
  const edges = samplePayload().edges;
  assert.equal(
    hitTestNode({ x: 0, y: 0 }, nodes, positions, identityViewport()),
    1,
  );
  assert.equal(
    hitTestNode({ x: 500, y: 500 }, nodes, positions, identityViewport()),
    null,
  );
  assert.ok(hitTestEdge({ x: 50, y: 0 }, edges, positions, identityViewport()));
  assert.equal(
    hitTestEdge({ x: 50, y: 90 }, edges, positions, identityViewport()),
    null,
  );
  assert.equal(typeof drawGraph, "function");
});

test("path explorer finds shortest paths and tracks history", () => {
  const payload = samplePayload();
  const adjacency = buildAdjacency(payload);
  assert.equal(adjacency.get(1)?.length, 3);
  const directed = buildAdjacency(payload, { directed: true });
  assert.equal(directed.get(5)?.length, 0);
  const path = findGraphPath(payload, 1, 5);
  assert.ok(path);
  assert.deepEqual(path.node_ids, [1, 2, 3, 5]);
  assert.equal(path.hops, 3);
  assert.deepEqual(pathNodeIds(path), new Set([1, 2, 3, 5]));
  assert.equal(pathEdgeKeys(path).size, 3);
  assert.deepEqual(pathKinds(path), ["link", "tag"]);
  assert.equal(pathSummary(path).status, "connected");
  assert.equal(pathSummary(null).status, "disconnected");
  assert.equal(findGraphPath(payload, 5, 4, { directed: true }), null);
  assert.deepEqual(findGraphPath(payload, 2, 2)?.node_ids, [2]);
  assert.deepEqual([...depthMap(payload, 1).keys()].sort(), [1, 2, 3, 4, 5, 6]);
  assert.equal(reachableCount(payload, 99), 1);
  const history = pushPathHistory([], path);
  assert.equal(history.length, 1);
  assert.equal(pushPathHistory(history, path).length, 1);
  assert.equal(pushPathHistory([], null).length, 0);
});

test("inspector builds groups, stats, breadcrumbs, and navigation state", () => {
  const payload = samplePayload();
  const model = buildInspectorModel(payload, 2);
  assert.ok(model);
  assert.equal(model.degree, 2);
  assert.equal(model.neighbors.length, 1);
  assert.equal(
    groupNeighbors(model.neighbors.flatMap((group) => group.nodes)).length,
    1,
  );
  assert.deepEqual(inspectorStats(payload, 1), {
    degree: 3,
    incoming: 1,
    outgoing: 2,
    unresolved: 1,
  });
  assert.equal(breadcrumbs(payload.nodes[0]).length, 3);
  assert.equal(truncateLabel("abcdefgh", 5), "abcd…");
  assert.equal(formatScore(0.01234), "0.012");
  assert.equal(formatCount(1, "link"), "1 link");
  assert.equal(formatCount(2, "link"), "2 links");
  assert.equal(buildInspectorModel(payload, 999), null);
  let state = defaultInspectorState();
  assert.equal(state.selectedId, null);
  state = selectInspectorNode(state, 2);
  state = toggleInspectorSection(state, "note");
  assert.equal(state.expanded.note, true);
  state = toggleInspectorSection(state, "note");
  assert.equal(state.expanded.note, false);
  const nodes = payload.nodes;
  assert.equal(nextInspectorSelection(state, nodes, 1).selectedId, 3);
  assert.equal(nextInspectorSelection(state, nodes, -1).selectedId, 1);
  assert.equal(nextInspectorSelection(state, [], 1).selectedId, 2);
});

test("graph api client calls the expected v2 graph methods", async () => {
  const calls: Array<{ method: string; body: Record<string, unknown> }> = [];
  const fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = url.split("/").pop() ?? "";
    calls.push({
      method,
      body: JSON.parse(String(init.body)) as Record<string, unknown>,
    });
    const payloadByMethod: Record<string, unknown> = {
      "graph.overview": {
        ok: true,
        data: { stats: {}, metrics: { nodes: 6 }, tags: ["web"] },
      },
      "graph.nodes": {
        ok: true,
        data: { items: samplePayload().nodes, page: {} },
      },
      "graph.edges": {
        ok: true,
        data: { items: samplePayload().edges, page: {} },
      },
      "graph.layout": { ok: true, data: samplePayload() },
      "graph.path": { ok: true, data: { node_ids: [1, 2], cost: 1, hops: 1 } },
      "graph.neighbors": { ok: true, data: samplePayload() },
      "graph.backlinks": { ok: true, data: { backlinks: [] } },
      "graph.outlinks": {
        ok: true,
        data: { node_id: 1, backlinks: [], outlinks: [], unresolved: [] },
      },
      "graph.centrality": {
        ok: true,
        data: { items: [{ id: 1, score: 0.5 }] },
      },
      "graph.components": {
        ok: true,
        data: { count: 1, items: [{ size: 6 }] },
      },
      "graph.communities": {
        ok: true,
        data: { count: 1, items: [{ size: 6 }] },
      },
      "graph.cycles": { ok: true, data: { count: 0, items: [] } },
      "graph.recommend": { ok: true, data: { missing_links: [], popular: [] } },
      "graph.related": { ok: true, data: { items: [] } },
      "graph.insights": { ok: true, data: { flags: [] } },
      "graph.snapshot.create": { ok: true, data: { meta: { id: "s1" } } },
      "graph.snapshot.list": { ok: true, data: { snapshots: [] } },
      "graph.resolve": { ok: true, data: { id: 7 } },
    };
    return new Response(
      JSON.stringify(payloadByMethod[method] ?? { ok: true, data: {} }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  }) as typeof globalThis.fetch;
  const client = new GraphApiClient(new V2Client({ fetch }));
  assert.equal((await client.overview()).tags[0], "web");
  assert.equal((await client.nodes()).length, 6);
  assert.equal((await client.edges()).length, 5);
  assert.equal((await client.layout()).nodes.length, 6);
  assert.equal((await client.path(1, 2)).hops, 1);
  assert.equal((await client.neighbors(1)).nodes.length, 6);
  assert.deepEqual(await client.backlinks(1), []);
  assert.equal((await client.outlinks(1)).node_id, 1);
  assert.equal((await client.centrality())[0].id, 1);
  assert.equal((await client.components())[0].size, 6);
  assert.equal((await client.communities())[0].size, 6);
  assert.deepEqual(await client.cycles(), []);
  assert.deepEqual(await client.recommendations(), []);
  assert.deepEqual(await client.related(1), []);
  assert.deepEqual(await client.insights(), { flags: [] });
  assert.equal((await client.capture("test")).id, "s1");
  assert.deepEqual(await client.snapshots(), []);
  assert.equal(await client.resolve("Alpha"), 7);
  assert.ok(calls.length >= 18);
  assert.ok(
    calls.some(
      (call) => call.method === "graph.path" && call.body.weighted === false,
    ),
  );
});

test("graph data constants expose all supported kinds", () => {
  assert.deepEqual(GRAPH_NODE_KINDS, ["note", "folder", "reference", "tag"]);
  assert.deepEqual(GRAPH_EDGE_KINDS, ["parent", "link", "tag", "mention"]);
  const link: GraphLinkDetail = {
    node_id: 1,
    backlinks: [],
    outlinks: [],
    unresolved: [],
    in_degree: 0,
    out_degree: 0,
  };
  assert.equal(link.node_id, 1);
  const recommendations: GraphRecommendation[] = [];
  assert.equal(recommendations.length, 0);
});
