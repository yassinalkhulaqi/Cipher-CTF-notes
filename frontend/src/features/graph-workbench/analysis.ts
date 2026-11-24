/** Pathfinding and structural analysis used by the path explorer. */

import type {
  ArticulationResult,
  Bridge,
  Component,
  CutVertex,
  GraphEdge,
  GraphPayload,
  PathResult,
  PathStep,
} from "./types";

export type Adjacency = Record<string, Record<string, GraphEdge>>;

export function buildAdjacency(
  graph: GraphPayload,
  directed = false,
  kinds: string[] = [],
): Adjacency {
  const allowed = new Set(kinds);
  const adjacency: Adjacency = {};
  for (const node of graph.nodes) adjacency[node.id] = {};
  for (const edge of graph.edges) {
    if (allowed.size > 0 && !allowed.has(edge.kind)) continue;
    const pairs: Array<[string, string]> = directed
      ? [[edge.source, edge.target]]
      : [
          [edge.source, edge.target],
          [edge.target, edge.source],
        ];
    for (const [from, to] of pairs) {
      if (!adjacency[from] || !adjacency[to]) continue;
      const current = adjacency[from][to];
      if (!current || edge.weight < current.weight) adjacency[from][to] = edge;
    }
  }
  return adjacency;
}

export function adjacencyKeys(adjacency: Adjacency): string[] {
  return Object.keys(adjacency).sort();
}

export function nodeLabel(graph: GraphPayload, id: string): string {
  return graph.nodes.find((node) => node.id === id)?.label ?? id;
}

function explainStep(
  graph: GraphPayload,
  edge: GraphEdge,
  from: string,
  to: string,
  index: number,
): string {
  const origin = nodeLabel(graph, from);
  const destination = nodeLabel(graph, to);
  const relation = edge.label || edge.kind;
  const direction = edge.source === from ? "points to" : "is referenced by";
  return `Step ${index}: ${origin} ${direction} ${destination} via ${relation} (weight ${edge.weight.toFixed(2)})`;
}

export function shortestPath(
  graph: GraphPayload,
  source: string,
  target: string,
  options: {
    directed?: boolean;
    weighted?: boolean;
    maxHops?: number | null;
  } = {},
): PathResult {
  const directed = options.directed ?? false;
  const weighted = options.weighted ?? false;
  const maxHops = options.maxHops ?? null;
  const base: PathResult = {
    source,
    target,
    found: false,
    nodeIds: [],
    steps: [],
    explanations: [],
    hops: 0,
    cost: 0,
    directed,
    weighted,
    maxHops,
  };
  if (!graph.nodes.some((node) => node.id === source)) return base;
  if (!graph.nodes.some((node) => node.id === target)) return base;
  if (source === target) {
    return { ...base, found: true, nodeIds: [source] };
  }
  const adjacency = buildAdjacency(graph, directed);
  const costs: Record<string, number> = { [source]: 0 };
  const hops: Record<string, number> = { [source]: 0 };
  const previous: Record<string, [string, GraphEdge]> = {};
  const queue: Array<[number, string]> = [[0, source]];
  while (queue.length > 0) {
    queue.sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
    const [cost, current] = queue.shift() as [number, string];
    if (cost > (costs[current] ?? Number.POSITIVE_INFINITY)) continue;
    if (current === target) break;
    if (maxHops !== null && hops[current] >= maxHops) continue;
    for (const neighbor of Object.keys(adjacency[current]).sort()) {
      if (neighbor === source) continue;
      const edge = adjacency[current][neighbor];
      const stepCost = weighted ? 1 / Math.max(edge.weight, 0.05) : 1;
      const candidate = cost + stepCost;
      const candidateHops = hops[current] + 1;
      const known = costs[neighbor];
      if (
        known !== undefined &&
        (candidate > known + 1e-12 || candidateHops > hops[neighbor])
      ) {
        continue;
      }
      costs[neighbor] = candidate;
      hops[neighbor] = candidateHops;
      previous[neighbor] = [current, edge];
      queue.push([candidate, neighbor]);
    }
  }
  if (!previous[target]) return base;
  const chain: string[] = [target];
  const traversed: GraphEdge[] = [];
  let cursor = target;
  while (cursor !== source) {
    const [parent, edge] = previous[cursor];
    traversed.push(edge);
    chain.push(parent);
    cursor = parent;
  }
  chain.reverse();
  traversed.reverse();
  const steps: PathStep[] = traversed.map((edge, index) => ({
    index: index + 1,
    source: chain[index],
    target: chain[index + 1],
    kind: edge.kind,
    label: edge.label,
    weight: edge.weight,
    direction: edge.source === chain[index] ? "forward" : "reverse",
    explanation: explainStep(
      graph,
      edge,
      chain[index],
      chain[index + 1],
      index + 1,
    ),
  }));
  return {
    ...base,
    found: true,
    nodeIds: chain,
    steps,
    explanations: steps.map((step) => step.explanation),
    hops: chain.length - 1,
    cost: costs[target],
  };
}

export function connectedComponents(graph: GraphPayload): Component[] {
  const adjacency = buildAdjacency(graph);
  const visited = new Set<string>();
  const groups: string[][] = [];
  for (const start of adjacencyKeys(adjacency)) {
    if (visited.has(start)) continue;
    visited.add(start);
    const queue = [start];
    const members: string[] = [];
    while (queue.length > 0) {
      const current = queue.shift() as string;
      members.push(current);
      for (const neighbor of Object.keys(adjacency[current]).sort()) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
    groups.push(members.sort());
  }
  groups.sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]));
  return groups.map((group, index) => ({
    index: index + 1,
    nodeIds: group,
    size: group.length,
  }));
}

interface TarjanState {
  discovery: Record<string, number>;
  low: Record<string, number>;
  parent: Record<string, string>;
  children: Record<string, number>;
  root: Record<string, string>;
  timer: number;
}

function tarjan(adjacency: Adjacency): TarjanState {
  const state: TarjanState = {
    discovery: {},
    low: {},
    parent: {},
    children: {},
    root: {},
    timer: 0,
  };
  for (const start of adjacencyKeys(adjacency)) {
    if (state.discovery[start] !== undefined) continue;
    state.discovery[start] = state.low[start] = state.timer;
    state.timer += 1;
    state.root[start] = start;
    const stack: Array<[string, string[], number]> = [
      [start, Object.keys(adjacency[start]).sort(), 0],
    ];
    while (stack.length > 0) {
      const frame = stack[stack.length - 1];
      const [node, neighbors, index] = frame;
      if (index < neighbors.length) {
        frame[2] += 1;
        const neighbor = neighbors[index];
        if (state.discovery[neighbor] === undefined) {
          state.parent[neighbor] = node;
          state.children[node] = (state.children[node] ?? 0) + 1;
          state.root[neighbor] = state.root[node];
          state.discovery[neighbor] = state.low[neighbor] = state.timer;
          state.timer += 1;
          stack.push([neighbor, Object.keys(adjacency[neighbor]).sort(), 0]);
        } else if (neighbor !== state.parent[node]) {
          state.low[node] = Math.min(
            state.low[node],
            state.discovery[neighbor],
          );
        }
        continue;
      }
      stack.pop();
      const parent = state.parent[node];
      if (parent !== undefined) {
        state.low[parent] = Math.min(state.low[parent], state.low[node]);
      }
    }
  }
  return state;
}

export function articulationPoints(graph: GraphPayload): CutVertex[] {
  const adjacency = buildAdjacency(graph);
  const state = tarjan(adjacency);
  const found = new Set<string>();
  for (const node of adjacencyKeys(adjacency)) {
    const parent = state.parent[node];
    if (parent === undefined) continue;
    const rootChild = state.root[node] === parent;
    if (rootChild && (state.children[parent] ?? 0) > 1) found.add(parent);
    if (!rootChild && state.low[node] >= state.discovery[parent])
      found.add(parent);
  }
  const originalComponents = connectedComponents(graph).length;
  const result: CutVertex[] = [];
  for (const id of Array.from(found).sort()) {
    const reduced: GraphPayload = {
      nodes: graph.nodes.filter((node) => node.id !== id),
      edges: graph.edges.filter(
        (edge) => edge.source !== id && edge.target !== id,
      ),
    };
    const fragments = connectedComponents(reduced);
    if (fragments.length <= originalComponents) continue;
    const count = fragments.length;
    result.push({
      nodeId: id,
      label: nodeLabel(graph, id),
      componentCount: count,
      isolatedCount: fragments.filter((fragment) => fragment.size === 1).length,
      fragments: fragments.map((fragment) => fragment.nodeIds),
      severity: count >= 4 ? "critical" : count === 3 ? "high" : "medium",
    });
  }
  return result;
}

export function bridgeList(graph: GraphPayload): Bridge[] {
  const adjacency = buildAdjacency(graph);
  const state = tarjan(adjacency);
  const result: Bridge[] = [];
  for (const edge of graph.edges) {
    const forward =
      state.parent[edge.target] === edge.source &&
      state.low[edge.target] > state.discovery[edge.source];
    const backward =
      state.parent[edge.source] === edge.target &&
      state.low[edge.source] > state.discovery[edge.target];
    if (forward || backward) {
      result.push({
        source: edge.source,
        target: edge.target,
        kind: edge.kind,
        key: [edge.source, edge.target, edge.kind],
      });
    }
  }
  return result.sort((a, b) => a.key.join("|").localeCompare(b.key.join("|")));
}

export function neighborhood(
  graph: GraphPayload,
  id: string,
  depth = 1,
): GraphPayload {
  const adjacency = buildAdjacency(graph);
  if (!adjacency[id]) return { nodes: [], edges: [] };
  const visited = new Set<string>([id]);
  let frontier = new Set<string>([id]);
  for (let step = 0; step < Math.min(depth, 6); step += 1) {
    const following = new Set<string>();
    for (const key of frontier) {
      for (const neighbor of Object.keys(adjacency[key]))
        following.add(neighbor);
    }
    frontier = new Set(
      Array.from(following).filter((key) => !visited.has(key)),
    );
    for (const key of frontier) visited.add(key);
    if (frontier.size === 0) break;
  }
  return {
    nodes: graph.nodes.filter((node) => visited.has(node.id)),
    edges: graph.edges.filter(
      (edge) => visited.has(edge.source) && visited.has(edge.target),
    ),
  };
}

export function structuralSummary(
  graph: GraphPayload,
): ArticulationResult["summary"] {
  const components = connectedComponents(graph);
  const degrees = graph.nodes.map(
    (node) =>
      graph.edges.filter(
        (edge) => edge.source === node.id || edge.target === node.id,
      ).length,
  );
  const pairCount = (graph.nodes.length * (graph.nodes.length - 1)) / 2;
  return {
    nodes: graph.nodes.length,
    edges: graph.edges.length,
    components: components.length,
    largestComponent: Math.max(
      0,
      ...components.map((component) => component.size),
    ),
    isolated: components.filter((component) => component.size === 1).length,
    cutVertices: articulationPoints(graph).length,
    bridges: bridgeList(graph).length,
    averageDegree:
      degrees.length > 0
        ? Math.round(
            (degrees.reduce((sum, value) => sum + value, 0) / degrees.length) *
              1000,
          ) / 1000
        : 0,
    density:
      pairCount > 0
        ? Math.round((graph.edges.length / pairCount) * 10000) / 10000
        : 0,
  };
}

export function pathSummary(result: PathResult): string {
  if (!result.found)
    return "No relationship path found between these entities.";
  if (result.hops === 0) return "Source and target are the same entity.";
  return `${result.hops} hop${result.hops === 1 ? "" : "s"} · cost ${result.cost.toFixed(2)}`;
}

export function cutVertexSummary(cut: CutVertex): string {
  return `${cut.label} separates ${cut.componentCount} groups${cut.isolatedCount ? ` (${cut.isolatedCount} isolated)` : ""}`;
}

export function stepTone(step: PathStep): string {
  if (step.kind === "evidences" || step.kind === "derives") return "evidence";
  if (step.kind === "supersedes" || step.kind === "duplicates") return "warn";
  return "neutral";
}
