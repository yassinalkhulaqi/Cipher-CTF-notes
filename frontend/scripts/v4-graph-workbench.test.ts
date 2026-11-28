import assert from "node:assert/strict";
import test from "node:test";

import { V4ApiError, V4Client } from "../src/features/v4-kernel/client";
import {
  GraphWorkbenchClient,
  graphQueryString,
  type GraphEdgeDto,
  type GraphNodeDto,
  type GraphOverviewDto,
} from "../src/features/v4/graph-workbench/client";
import {
  clampWeight,
  filterSummary,
  fromFilterDto,
  initialGraphState,
  inspectNode,
  legendFor,
  metricsFromGraph,
  neighborsOf,
  parseLayout,
  reduceGraph,
  toFilterDto,
  toGraphQuery,
  uniqueKinds,
  visibleEdges,
  visibleNodes,
  type GraphSnapshotPayload,
  type GraphWorkbenchState,
} from "../src/features/v4/graph-workbench/state";

const NODES: GraphNodeDto[] = [
  { id: "a", kind: "note", label: "Alpha note", weight: 0.9 },
  { id: "b", kind: "target", label: "Beta host", weight: 0.7 },
  { id: "c", kind: "finding", label: "Gamma finding", weight: 0.5 },
  { id: "d", kind: "note", label: "Delta note", weight: 0.3 },
];

const EDGES: GraphEdgeDto[] = [
  { source: "a", target: "b", relation: "linked_to", weight: 0.9 },
  { source: "b", target: "c", relation: "derived_from", weight: 0.7 },
  { source: "a", target: "c", relation: "mentions", weight: 0.4 },
];

function payload(): GraphSnapshotPayload {
  return {
    nodes: NODES,
    edges: EDGES,
    legend: legendFor(EDGES),
    metrics: metricsFromGraph(NODES, EDGES),
    filter: null,
    hiddenNodes: 1,
    hiddenEdges: 0,
    total: 5,
  };
}

function loadedState(): GraphWorkbenchState {
  let state = reduceGraph(initialGraphState(), { type: "load-start" });
  state = reduceGraph(state, { type: "load-success", payload: payload() });
  return state;
}

function stubResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

test("initial state has typed defaults", () => {
  const state = initialGraphState();
  assert.equal(state.status, "idle");
  assert.equal(state.layout, "force");
  assert.deepEqual(state.filter.kinds, []);
  assert.equal(state.selectedNodeId, null);
  assert.equal(state.requestCount, 0);
});

test("reducer tracks the load lifecycle", () => {
  let state = initialGraphState();
  state = reduceGraph(state, { type: "load-start" });
  assert.equal(state.status, "loading");
  assert.equal(state.requestCount, 1);
  state = reduceGraph(state, { type: "load-success", payload: payload() });
  assert.equal(state.status, "ready");
  assert.equal(state.nodes.length, 4);
  assert.equal(state.hiddenNodes, 1);
  assert.equal(state.total, 5);
  assert.equal(state.metrics?.node_count, 4);
  assert.equal(state.legend.length, 3);
  state = reduceGraph(state, { type: "load-error", message: "boom" });
  assert.equal(state.status, "error");
  assert.equal(state.error, "boom");
  state = reduceGraph(state, { type: "set-status", status: "idle" });
  assert.equal(state.status, "idle");
});

test("load-success adopts the server filter", () => {
  const withFilter: GraphSnapshotPayload = {
    ...payload(),
    filter: {
      kinds: ["note"],
      relations: ["linked_to"],
      min_weight: 0.5,
      label_contains: "alpha",
    },
  };
  const state = reduceGraph(initialGraphState(), {
    type: "load-success",
    payload: withFilter,
  });
  assert.deepEqual(state.filter.kinds, ["note"]);
  assert.deepEqual(state.filter.relations, ["linked_to"]);
  assert.equal(state.filter.minWeight, 0.5);
  assert.equal(state.filter.labelContains, "alpha");
});

test("reducer filter actions are immutable and normalized", () => {
  const original = loadedState();
  const toggled = reduceGraph(original, {
    type: "toggle-kind",
    kind: " NOTE ",
  });
  assert.deepEqual(toggled.filter.kinds, ["note"]);
  assert.deepEqual(original.filter.kinds, []);
  const removed = reduceGraph(toggled, { type: "toggle-kind", kind: "note" });
  assert.deepEqual(removed.filter.kinds, []);
  const relation = reduceGraph(original, {
    type: "toggle-relation",
    relation: "MENTIONS",
  });
  assert.deepEqual(relation.filter.relations, ["mentions"]);
  const blank = reduceGraph(original, { type: "toggle-kind", kind: " " });
  assert.deepEqual(blank.filter, original.filter);
});

test("weight clamping and label truncation", () => {
  const state = loadedState();
  assert.equal(clampWeight(2), 1);
  assert.equal(clampWeight(-4), 0);
  assert.equal(clampWeight(Number.NaN), 0);
  assert.equal(clampWeight(0.42), 0.42);
  const bounded = reduceGraph(state, { type: "set-min-weight", value: 7 });
  assert.equal(bounded.filter.minWeight, 1);
  const labelled = reduceGraph(state, {
    type: "set-label",
    value: "x".repeat(200),
  });
  assert.equal(labelled.filter.labelContains.length, 120);
  const reset = reduceGraph(bounded, { type: "reset-filter" });
  assert.equal(reset.filter.minWeight, 0);
  assert.equal(reset.selectedNodeId, null);
});

test("selection, hover, paging and layout actions", () => {
  let state = loadedState();
  state = reduceGraph(state, { type: "select-node", nodeId: "b" });
  assert.equal(state.selectedNodeId, "b");
  state = reduceGraph(state, { type: "hover-node", nodeId: "c" });
  assert.equal(state.hoveredNodeId, "c");
  state = reduceGraph(state, { type: "set-page", page: -3 });
  assert.equal(state.page, 1);
  state = reduceGraph(state, { type: "set-page", page: 2.8 });
  assert.equal(state.page, 2);
  state = reduceGraph(state, { type: "set-layout", layout: "GRID" });
  assert.equal(state.layout, "grid");
  state = reduceGraph(state, {
    type: "set-points",
    points: [{ node_id: "a", x: 10, y: 20 }],
  });
  assert.equal(state.points.a.x, 10);
  state = reduceGraph(state, { type: "select-node", nodeId: null });
  assert.equal(state.selectedNodeId, null);
});

test("client-side visibility mirrors filter semantics", () => {
  let state = loadedState();
  assert.equal(visibleNodes(state).length, 4);
  assert.equal(visibleEdges(state).length, 3);
  state = reduceGraph(state, { type: "toggle-kind", kind: "note" });
  assert.deepEqual(
    visibleNodes(state).map((node) => node.id),
    ["a", "d"],
  );
  assert.equal(visibleEdges(state).length, 0);
  state = reduceGraph(state, { type: "reset-filter" });
  state = reduceGraph(state, { type: "set-min-weight", value: 0.6 });
  assert.deepEqual(
    visibleEdges(state).map((edge) => edge.relation),
    ["linked_to", "derived_from"],
  );
  state = reduceGraph(state, { type: "toggle-relation", relation: "mentions" });
  assert.equal(visibleEdges(state).length, 0);
  state = reduceGraph(state, { type: "set-label", value: "BETA" });
  assert.deepEqual(
    visibleNodes(state).map((node) => node.id),
    ["b"],
  );
});

test("legend aggregation and unique kinds", () => {
  const legend = legendFor([...EDGES, EDGES[0]]);
  assert.equal(legend[0].relation, "linked_to");
  assert.equal(legend[0].count, 2);
  assert.equal(legend[0].average_weight, 0.9);
  assert.equal(legend.length, 3);
  assert.deepEqual(uniqueKinds(NODES), ["finding", "note", "target"]);
});

test("neighbour lookup and node inspection", () => {
  const state = loadedState();
  assert.deepEqual(neighborsOf(state, "a"), ["b", "c"]);
  assert.deepEqual(neighborsOf(state, "d"), []);
  const inspected = inspectNode(state, "b");
  assert.ok(inspected);
  assert.equal(inspected.degree, 2);
  assert.equal(inspected.outgoing, 1);
  assert.equal(inspected.incoming, 1);
  assert.deepEqual(inspected.relations, ["derived_from", "linked_to"]);
  assert.equal(inspectNode(state, "missing"), null);
  assert.equal(inspectNode(state, null), null);
});

test("local metrics match graph structure", () => {
  const metrics = metricsFromGraph(NODES, EDGES);
  assert.equal(metrics.node_count, 4);
  assert.equal(metrics.edge_count, 3);
  assert.equal(metrics.component_count, 2);
  assert.equal(metrics.isolated_count, 1);
  assert.equal(metrics.max_degree, 2);
  assert.equal(metrics.average_degree, 1.5);
  assert.equal(metrics.density, 0.5);
  assert.equal(metricsFromGraph([], []).component_count, 0);
});

test("filter summary and query conversion", () => {
  let state = loadedState();
  assert.equal(filterSummary(state), "No filters applied");
  state = reduceGraph(state, { type: "toggle-kind", kind: "note" });
  state = reduceGraph(state, {
    type: "toggle-relation",
    relation: "linked_to",
  });
  state = reduceGraph(state, { type: "set-min-weight", value: 0.5 });
  state = reduceGraph(state, { type: "set-label", value: "alpha" });
  assert.match(filterSummary(state), /kinds: note/);
  assert.match(filterSummary(state), /relations: linked_to/);
  assert.match(filterSummary(state), /weight/);
  assert.match(filterSummary(state), /label/);
  const query = toGraphQuery(state);
  assert.equal(query.layout, "force");
  assert.deepEqual(query.kinds, ["note"]);
  assert.equal(query.minWeight, 0.5);
});

test("filter DTO round trip and layout parsing", () => {
  const state = loadedState();
  const dto = toFilterDto(state.filter);
  assert.equal(dto.min_weight, 0);
  assert.deepEqual(fromFilterDto(dto), state.filter);
  assert.equal(parseLayout("CIRCULAR"), "circular");
  assert.equal(parseLayout("grid"), "grid");
  assert.equal(parseLayout("unknown"), "force");
});

test("query string omits empty values and encodes lists", () => {
  assert.equal(graphQueryString(), "");
  const encoded = graphQueryString({
    page: 2,
    pageSize: 10,
    kinds: ["note", "target"],
    minWeight: 0,
    labelContains: "a b",
  });
  assert.match(encoded, /page=2/);
  assert.match(encoded, /page_size=10/);
  assert.match(encoded, /kinds=note%2Ctarget/);
  assert.match(encoded, /label_contains=a\+b/);
  assert.doesNotMatch(encoded, /min_weight/);
});

test("client decodes an overview envelope", async () => {
  const overview: GraphOverviewDto = {
    node_count: 4,
    edge_count: 3,
    component_count: 2,
    isolated_count: 1,
    density: 0.5,
    hidden_nodes: 0,
    hidden_edges: 0,
    legend: legendFor(EDGES),
    filter: { kinds: [], relations: [], min_weight: 0, label_contains: "" },
  };
  const envelope = {
    data: overview,
    meta: { request_id: "r1", version: "v4", page: 1, page_size: 50 },
  };
  const client = new GraphWorkbenchClient(
    new V4Client("/api/v4", (async () =>
      stubResponse(envelope)) as typeof fetch),
  );
  const result = await client.overview({ kinds: ["note"] });
  assert.equal(result.data.node_count, 4);
  assert.equal(result.meta.version, "v4");
});

test("client maps error envelopes to V4ApiError", async () => {
  const error = {
    error: { code: "invalid_input", message: "bad filter", details: ["kinds"] },
  };
  const client = new GraphWorkbenchClient(
    new V4Client("/api/v4", (async () =>
      stubResponse(error, 400)) as typeof fetch),
  );
  await assert.rejects(
    () => client.metrics({ minWeight: 4 }),
    (cause: unknown) =>
      cause instanceof V4ApiError && cause.code === "invalid_input",
  );
});

test("client builds path and snapshot requests", async () => {
  const requested: string[] = [];
  const fetchImpl = (async (input: RequestInfo | URL) => {
    requested.push(String(input));
    return stubResponse({
      data: {},
      meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
    });
  }) as typeof fetch;
  const client = new GraphWorkbenchClient(new V4Client("/api/v4", fetchImpl));
  await client.path({ source: "a", target: "b" });
  await client.snapshot("alpha-view");
  assert.match(requested[0], /\/graph\/path\?/);
  assert.match(requested[0], /source=a/);
  assert.match(requested[0], /target=b/);
  assert.equal(requested[1], "/api/v4/graph/snapshot?name=alpha-view");
});
