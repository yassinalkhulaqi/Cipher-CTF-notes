import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server.browser";

import {
  buildAdjacency,
  articulationPoints,
  bridgeList,
  connectedComponents,
  neighborhood,
  pathSummary,
  shortestPath,
  structuralSummary,
} from "../src/features/graph-workbench/analysis";
import {
  buildClusters,
  clusterCentroids,
  clusterChips,
  clusterColor,
  clusterSummary,
  filterByCluster,
  primaryKey,
} from "../src/features/graph-workbench/clusters";
import { GraphWorkbenchClient } from "../src/features/graph-workbench/client";
import {
  applyLocalEdge,
  canCommit,
  cancelGesture,
  commitGesture,
  describeGesture,
  draftToBody,
  draftToEdge,
  historySummary,
  initialGesture,
  initialHistory,
  pushEdit,
  redoEdit,
  removeLocalEdge,
  selectNode,
  setGestureKind,
  setGestureLabel,
  setGestureWeight,
  undoEdit,
  validateDraft,
} from "../src/features/graph-workbench/editor";
import {
  boundsOf,
  clamp,
  distance,
  edgeKey,
  fitViewport,
  identityViewport,
  nearestNode,
  panViewport,
  pointToSegment,
  screenToWorld,
  worldToScreen,
  zoomAt,
} from "../src/features/graph-workbench/geometry";
import { GraphWorkbench } from "../src/features/graph-workbench/GraphWorkbench";
import { ClusterChips } from "../src/features/graph-workbench/ClusterChips";
import { LayoutSwitcher } from "../src/features/graph-workbench/LayoutSwitcher";
import { PathExplorer } from "../src/features/graph-workbench/PathExplorer";
import {
  SeededRandom,
  computeLayout,
  forceLayout,
  hierarchicalLayout,
  hubOf,
  layoutSignature,
  radialLayout,
  stableHash,
  timelineLayout,
} from "../src/features/graph-workbench/layout";
import {
  centerViewportAt,
  minimapNodes,
  minimapToWorld,
  minimapTransform,
  viewportRect,
} from "../src/features/graph-workbench/minimap";
import {
  buildInspector,
  formatMetadata,
  formatTimestamp,
  groupNeighbors,
  inspectorSections,
  severityColor,
  truncateLabel,
} from "../src/features/graph-workbench/inspector";
import type { GraphPayload } from "../src/features/graph-workbench/types";
import {
  CLUSTER_DIMENSIONS,
  DEFAULT_LAYOUT_OPTIONS,
  KIND_COLORS,
  LAYOUT_KINDS,
  LINK_KINDS,
  isGraphPayload,
  layoutOptionsFrom,
} from "../src/features/graph-workbench/types";

type Node = GraphPayload["nodes"][number];
type Edge = GraphPayload["edges"][number];

function node(
  id: string,
  kind: string,
  tags: string[] = [],
  severity = "unknown",
  timestamp = 0,
): Node {
  return {
    id,
    ref: {
      kind: kind as Node["kind"],
      value: id.split(":")[1] ?? id,
      ref: id,
      label: id,
    },
    title: id,
    label: id,
    kind: kind as Node["kind"],
    tags,
    severity,
    status: "active",
    owner: "tester",
    summary: `summary for ${id}`,
    metadata: {},
    timestamp,
    version: 1,
  };
}

function edge(
  source: string,
  target: string,
  kind = "relates",
  label = "",
  weight = 1,
): Edge {
  return {
    source,
    target,
    kind: kind as Edge["kind"],
    label,
    weight,
    metadata: {},
  };
}

function sample(): GraphPayload {
  return {
    nodes: [
      node("note:root", "note", ["alpha", "severity/high"], "high", 10),
      node("finding:sql", "finding", ["beta"], "critical", 20),
      node("evidence:cap", "evidence", ["alpha"], "low", 30),
      node("target:host", "target", ["beta"], "unknown", 40),
    ],
    edges: [
      edge("note:root", "finding:sql", "evidences", "supports"),
      edge("finding:sql", "evidence:cap", "derives"),
      edge("note:root", "target:host"),
    ],
  };
}

test("wire constants describe the workbench surface", () => {
  assert.deepEqual(LAYOUT_KINDS, [
    "force",
    "hierarchical",
    "radial",
    "timeline",
  ]);
  assert.deepEqual(CLUSTER_DIMENSIONS, ["tag", "kind", "severity"]);
  assert.equal(LINK_KINDS.length, 7);
  assert.ok(KIND_COLORS.note.startsWith("#"));
  assert.equal(layoutOptionsFrom({ seed: 5 }).seed, 5);
  assert.equal(isGraphPayload(sample()), true);
  assert.equal(isGraphPayload({ nodes: [] }), false);
});

test("seeded random and stable hash are deterministic", () => {
  assert.equal(stableHash("note:root"), stableHash("note:root"));
  assert.notEqual(stableHash("a"), stableHash("b"));
  const left = new SeededRandom(11);
  const right = new SeededRandom(11);
  assert.deepEqual(
    Array.from({ length: 6 }, () => left.nextU32()),
    Array.from({ length: 6 }, () => right.nextU32()),
  );
  assert.ok(new SeededRandom(3).random() >= 0);
  assert.equal(new SeededRandom(1).below(0), 0);
  assert.deepEqual(new SeededRandom(2).shuffle([1, 2, 3]).sort(), [1, 2, 3]);
});

test("all layout strategies are deterministic and bounded", () => {
  const graph = sample();
  const options = layoutOptionsFrom({ seed: 9 });
  for (const strategy of LAYOUT_KINDS) {
    const first = computeLayout(graph, strategy, options);
    const second = computeLayout(graph, strategy, options);
    assert.equal(layoutSignature(first), layoutSignature(second));
    assert.equal(Object.keys(first.positions).length, 4);
    for (const point of Object.values(first.positions)) {
      assert.ok(point.x >= 0 && point.x <= options.width);
      assert.ok(point.y >= 0 && point.y <= options.height);
    }
  }
  const left = computeLayout(graph, "force", layoutOptionsFrom({ seed: 1 }));
  const right = computeLayout(graph, "force", layoutOptionsFrom({ seed: 2 }));
  assert.notEqual(layoutSignature(left), layoutSignature(right));
});

test("raw layout helpers produce coordinates for every node", () => {
  const graph = sample();
  assert.equal(hubOf(graph), "finding:sql");
  assert.equal(
    Object.keys(forceLayout(graph, DEFAULT_LAYOUT_OPTIONS)).length,
    4,
  );
  assert.equal(
    Object.keys(hierarchicalLayout(graph, DEFAULT_LAYOUT_OPTIONS)).length,
    4,
  );
  assert.equal(
    Object.keys(radialLayout(graph, DEFAULT_LAYOUT_OPTIONS)).length,
    4,
  );
  assert.equal(
    Object.keys(timelineLayout(graph, DEFAULT_LAYOUT_OPTIONS)).length,
    4,
  );
  assert.ok(
    hierarchicalLayout(graph, layoutOptionsFrom({ root: "evidence:cap" }))[
      "evidence:cap"
    ],
  );
});

test("geometry helpers map world and screen coordinates", () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(distance({ x: 0, y: 0 }, { x: 3, y: 4 }), 5);
  assert.equal(
    pointToSegment({ x: 1, y: 1 }, { x: 0, y: 0 }, { x: 2, y: 0 }),
    1,
  );
  const viewport = identityViewport();
  const point = { x: 100, y: 40 };
  assert.deepEqual(
    screenToWorld(worldToScreen(point, viewport), viewport),
    point,
  );
  assert.notEqual(panViewport(viewport, 20, 10).x, viewport.x);
  assert.ok(zoomAt(viewport, point, 2).zoom > viewport.zoom);
  assert.deepEqual(boundsOf([]), {
    minX: 0,
    minY: 0,
    maxX: 0,
    maxY: 0,
    width: 0,
    height: 0,
  });
  const positions = computeLayout(
    sample(),
    "force",
    DEFAULT_LAYOUT_OPTIONS,
  ).positions;
  assert.equal(nearestNode(positions["note:root"], positions), "note:root");
  const fitted = fitViewport(positions, { width: 800, height: 500 });
  assert.ok(fitted.zoom > 0);
  assert.equal(edgeKey(sample().edges[0]), "note:root→finding:sql:evidences");
});

test("clustering groups by tag, kind, and severity", () => {
  const graph = sample();
  assert.equal(primaryKey(graph, "note:root", "tag"), "alpha");
  assert.equal(primaryKey(graph, "finding:sql", "kind"), "finding");
  assert.equal(primaryKey(graph, "finding:sql", "severity"), "critical");
  const tags = buildClusters(graph, "tag");
  assert.deepEqual(
    tags.clusters.map((cluster) => cluster.key),
    ["alpha", "beta"],
  );
  assert.equal(tags.assignments["evidence:cap"], "alpha");
  assert.equal(tags.unassigned.length, 0);
  assert.equal(filterByCluster(graph, tags, "alpha").nodes.length, 2);
  assert.equal(filterByCluster(graph, tags, "").nodes.length, 4);
  assert.equal(
    buildClusters(graph, "tag", "severity/").clusters[0].key,
    "severity/high",
  );
  assert.equal(clusterChips(tags, "alpha")[0].selected, true);
  assert.equal(clusterColor("alpha"), clusterColor("alpha"));
  assert.equal(clusterSummary(graph).severity, 4);
  const positions = computeLayout(
    graph,
    "radial",
    DEFAULT_LAYOUT_OPTIONS,
  ).positions;
  assert.ok(clusterCentroids(tags, positions).alpha);
});

test("shortest path explains each hop", () => {
  const graph = sample();
  const result = shortestPath(graph, "note:root", "evidence:cap");
  assert.equal(result.found, true);
  assert.deepEqual(result.nodeIds, [
    "note:root",
    "finding:sql",
    "evidence:cap",
  ]);
  assert.equal(result.hops, 2);
  assert.ok(
    result.steps[0].explanation.startsWith(
      "Step 1: note:root points to finding:sql",
    ),
  );
  assert.equal(result.explanations.length, 2);
  assert.ok(pathSummary(result).includes("2 hops"));
  assert.equal(shortestPath(graph, "note:root", "note:root").hops, 0);
  assert.equal(
    shortestPath(graph, "note:root", "finding:sql", { directed: false }).found,
    true,
  );
  assert.equal(shortestPath(graph, "note:root", "missing").found, false);
  assert.equal(
    shortestPath(graph, "note:root", "evidence:cap", { maxHops: 1 }).found,
    false,
  );
  assert.equal(
    buildAdjacency(graph)["note:root"]["finding:sql"].kind,
    "evidences",
  );
});

test("structural analysis finds articulation points and bridges", () => {
  const graph = sample();
  assert.equal(connectedComponents(graph).length, 1);
  const cuts = articulationPoints(graph)
    .map((cut) => cut.nodeId)
    .sort();
  assert.ok(cuts.includes("finding:sql"));
  assert.ok(bridgeList(graph).length >= 2);
  assert.equal(neighborhood(graph, "note:root", 1).nodes.length, 3);
  const summary = structuralSummary(graph);
  assert.equal(summary.nodes, 4);
  assert.equal(summary.edges, 3);
  assert.ok(summary.cutVertices >= 1);
});

test("relationship gestures walk source, target, and commit states", () => {
  let state = initialGesture();
  assert.equal(state.phase, "idle");
  state = selectNode(state, "note:root");
  assert.equal(state.phase, "source");
  state = selectNode(state, "finding:sql");
  assert.equal(state.phase, "target");
  state = setGestureKind(state, "references");
  state = setGestureLabel(state, "supports");
  state = setGestureWeight(state, 1.5);
  assert.equal(state.draft.weight, 1);
  assert.equal(canCommit(state), true);
  assert.ok(describeGesture(state).includes("references"));
  assert.equal(validateDraft(state.draft, sample()).length, 0);
  assert.equal(draftToBody(state.draft).source, "note:root");
  assert.equal(draftToEdge(state.draft).weight, 1);
  state = commitGesture(state);
  assert.equal(state.phase, "idle");
  assert.equal(cancelGesture(initialGesture()).phase, "idle");
});

test("draft validation rejects duplicates and bad endpoints", () => {
  const graph = sample();
  const duplicate = {
    source: "note:root",
    target: "finding:sql",
    kind: "evidences",
    label: "",
    weight: 1,
  };
  assert.ok(
    validateDraft(duplicate, graph).some((problem) =>
      problem.includes("already exists"),
    ),
  );
  assert.ok(
    validateDraft({ ...duplicate, source: "missing", target: "missing" }, graph)
      .length >= 2,
  );
  assert.ok(
    validateDraft(
      { ...duplicate, source: "note:root", target: "note:root" },
      graph,
    ).some((p) => p.includes("different")),
  );
});

test("relationship history supports undo and redo", () => {
  let history = initialHistory(2);
  const record = {
    action: "add",
    link: draftToEdge({
      source: "note:root",
      target: "evidence:cap",
      kind: "references",
      label: "",
      weight: 1,
    }),
    inverse: {},
    timestamp: 1,
    actor: "local",
  };
  history = pushEdit(history, record);
  assert.equal(history.undo.length, 1);
  assert.ok(historySummary(history).includes("last: add"));
  const graphWithEdge = applyLocalEdge(sample(), record.link);
  assert.equal(graphWithEdge.edges.length, 4);
  assert.equal(applyLocalEdge(graphWithEdge, record.link).edges.length, 4);
  const undone = undoEdit(history);
  assert.equal(undone.record?.action, "add");
  assert.equal(removeLocalEdge(graphWithEdge, record.link).edges.length, 3);
  const redone = redoEdit(undone.history);
  assert.equal(redone.record?.sequence, 1);
  assert.equal(redoEdit(redone.history).record, null);
  history = pushEdit(pushEdit(pushEdit(history, record), record), record);
  assert.equal(history.undo.length, 2);
});

test("minimap projection and viewport rectangles stay inside the map", () => {
  const positions = computeLayout(
    sample(),
    "force",
    DEFAULT_LAYOUT_OPTIONS,
  ).positions;
  const size = { width: 220, height: 140 };
  const transform = minimapTransform(positions, size);
  const dots = minimapNodes(positions, transform);
  assert.equal(dots.length, 4);
  for (const dot of dots) {
    assert.ok(dot.point.x >= 0 && dot.point.x <= size.width);
    assert.ok(dot.point.y >= 0 && dot.point.y <= size.height);
  }
  const world = minimapToWorld(dots[0].point, transform);
  const centered = centerViewportAt(identityViewport(), world, {
    width: 1200,
    height: 760,
  });
  assert.ok(Number.isFinite(centered.x));
  const rect = viewportRect(centered, transform);
  assert.ok(rect.width > 0 && rect.height > 0);
});

test("inspector formats metadata and neighbor groups", () => {
  const graph = sample();
  const detail = {
    entityId: "note:root",
    title: "Root",
    status: "active",
    tags: ["alpha"],
    summary: "summary",
    owner: "tester",
    createdAt: 1,
    updatedAt: 2,
    version: 3,
    metadata: { severity: "high", count: 4, nested: { a: true } },
  };
  const model = buildInspector(graph.nodes[0], detail, {
    degree: 2,
    neighbors: [
      { id: "finding:sql", label: "finding:sql" },
      { id: "target:host", label: "target:host" },
    ],
    clusters: { tag: "alpha" },
  });
  assert.equal(model.title, "Root");
  assert.equal(model.version, 3);
  assert.deepEqual(inspectorSections(model), [
    "identity",
    "relationships",
    "tags",
    "clusters",
    "metadata",
  ]);
  assert.equal(formatMetadata({ z: 1, a: "x" })[0].key, "a");
  assert.equal(severityColor("critical"), "#fb7185");
  assert.equal(truncateLabel("a".repeat(60)).length, 42);
  assert.equal(formatTimestamp(0), "—");
  assert.deepEqual(
    Object.keys(groupNeighbors(model.neighbors, graph.nodes)).sort(),
    ["finding", "target"],
  );
});

test("client calls graph namespace actions with envelopes", async () => {
  const calls: Array<{ url: string; body: string }> = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    calls.push({ url: String(input), body: String(init.body ?? "") });
    return new Response(
      JSON.stringify({
        data: {
          strategy: "radial",
          positions: {},
          seed: 1,
          width: 1200,
          height: 760,
          center: "",
        },
        meta: { request_id: "r1", api_version: "3.0" },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof globalThis.fetch;
  const client = new GraphWorkbenchClient({
    fetch: fetchImpl,
    basePath: "/api/v3",
  });
  const result = await client.layout("radial", { seed: 1 });
  assert.equal(result.strategy, "radial");
  assert.equal(calls[0].url, "/api/v3/graph/layout");
  assert.ok(calls[0].body.includes("radial"));
});

test("components render stable data attributes", () => {
  const layoutMarkup = renderToStaticMarkup(
    createElement(LayoutSwitcher, {
      value: "force",
      onChange: () => undefined,
    }),
  );
  assert.ok(layoutMarkup.includes('data-layout="force"'));
  assert.ok(layoutMarkup.includes('aria-pressed="true"'));

  const chipsMarkup = renderToStaticMarkup(
    createElement(ClusterChips, {
      chips: [
        {
          key: "alpha",
          label: "alpha",
          count: 2,
          color: "#38bdf8",
          dimension: "tag",
          selected: true,
        },
      ],
      selected: "alpha",
      dimension: "tag",
      onSelect: () => undefined,
      onDimension: () => undefined,
    }),
  );
  assert.ok(chipsMarkup.includes('data-cluster="alpha"'));
  assert.ok(chipsMarkup.includes('data-selected="true"'));

  const pathMarkup = renderToStaticMarkup(
    createElement(PathExplorer, {
      result: shortestPath(sample(), "note:root", "evidence:cap"),
      source: "note:root",
      target: "evidence:cap",
      nodes: sample().nodes,
      onSource: () => undefined,
      onTarget: () => undefined,
      onFind: () => undefined,
    }),
  );
  assert.ok(pathMarkup.includes('data-testid="gw-path-step"'));
  assert.ok(pathMarkup.includes("Step 1"));

  const workbenchMarkup = renderToStaticMarkup(
    createElement(GraphWorkbench, { initialGraph: sample() }),
  );
  assert.ok(workbenchMarkup.includes('data-testid="gw-root"'));
  assert.ok(workbenchMarkup.includes('data-testid="gw-canvas"'));
  assert.ok(workbenchMarkup.includes('data-testid="gw-minimap"'));
  assert.ok(workbenchMarkup.includes('data-testid="gw-path-explorer"'));
});
