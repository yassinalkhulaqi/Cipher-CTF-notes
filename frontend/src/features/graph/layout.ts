import {
  add,
  centroid,
  distance,
  normalize,
  scale,
  spiralPoint,
  subtract,
} from "./geometry";
import type {
  GraphEdge,
  GraphNode,
  LayoutKind,
  LayoutOptions,
  Point,
} from "./types";
import { DEFAULT_LAYOUT } from "./types";

export type PositionMap = Map<number, Point>;

export function hashSeed(value: string | number): number {
  const text = String(value);
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function createRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let result = state;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

export function optionsWithDefaults(
  options: Partial<LayoutOptions> = {},
): LayoutOptions {
  return { ...DEFAULT_LAYOUT, ...options };
}

export function initialPositions(
  nodes: GraphNode[],
  seed: number,
): PositionMap {
  const positions: PositionMap = new Map();
  const random = createRandom(seed);
  nodes.forEach((node, index) => {
    const point = spiralPoint(index, 34);
    positions.set(node.id, {
      x: point.x + (random() - 0.5) * 12,
      y: point.y + (random() - 0.5) * 12,
    });
  });
  return positions;
}

function adjacency(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<number, number[]> {
  const ids = new Set(nodes.map((node) => node.id));
  const map = new Map<number, number[]>();
  for (const node of nodes) map.set(node.id, []);
  for (const edge of edges) {
    if (
      !ids.has(edge.source) ||
      !ids.has(edge.target) ||
      edge.source === edge.target
    )
      continue;
    map.get(edge.source)?.push(edge.target);
    map.get(edge.target)?.push(edge.source);
  }
  for (const list of map.values()) list.sort((a, b) => a - b);
  return map;
}

export function forceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: Partial<LayoutOptions> = {},
): PositionMap {
  const settings = optionsWithDefaults(options);
  const positions = initialPositions(nodes, settings.seed);
  if (nodes.length < 2) return positions;
  const cooling = Math.max(1, settings.iterations);
  for (let step = 0; step < cooling; step += 1) {
    const temperature = Math.max(0.02, 1 - step / cooling);
    const forces: PositionMap = new Map(
      nodes.map((node) => [node.id, { x: 0, y: 0 }]),
    );

    for (let first = 0; first < nodes.length; first += 1) {
      for (let second = first + 1; second < nodes.length; second += 1) {
        const left = nodes[first];
        const right = nodes[second];
        const a = positions.get(left.id);
        const b = positions.get(right.id);
        if (!a || !b) continue;
        const delta = subtract(a, b);
        const separation = Math.max(distance(a, b), 1);
        const magnitude = settings.repulsion / (separation * separation);
        const force = scale(normalize(delta), magnitude);
        forces.set(left.id, add(forces.get(left.id) ?? { x: 0, y: 0 }, force));
        forces.set(
          right.id,
          subtract(forces.get(right.id) ?? { x: 0, y: 0 }, force),
        );
      }
    }

    for (const edge of edges) {
      const a = positions.get(edge.source);
      const b = positions.get(edge.target);
      if (!a || !b) continue;
      const delta = subtract(b, a);
      const separation = Math.max(distance(a, b), 1);
      const target =
        settings.linkDistance * Math.max(0.5, Math.min(2, edge.weight ?? 1));
      const magnitude = (separation - target) * 0.08;
      const force = scale(normalize(delta), magnitude);
      forces.set(
        edge.source,
        add(forces.get(edge.source) ?? { x: 0, y: 0 }, force),
      );
      forces.set(
        edge.target,
        subtract(forces.get(edge.target) ?? { x: 0, y: 0 }, force),
      );
    }

    for (const node of nodes) {
      const point = positions.get(node.id);
      const force = forces.get(node.id);
      if (!point || !force) continue;
      const gravity = scale(point, settings.centerGravity);
      const combined = subtract(force, gravity);
      const stepSize = Math.min(24, 6 * temperature);
      positions.set(
        node.id,
        add(
          point,
          scale(
            normalize(combined),
            Math.min(stepSize, distance(point, add(point, combined))),
          ),
        ),
      );
    }
  }
  return positions;
}

export function circleLayout(
  nodes: GraphNode[],
  options: Partial<LayoutOptions> = {},
): PositionMap {
  const settings = optionsWithDefaults(options);
  const positions: PositionMap = new Map();
  const radius = Math.max(70, settings.width / 3);
  nodes.forEach((node, index) => {
    const angle =
      (index * Math.PI * 2) / Math.max(1, nodes.length) - Math.PI / 2;
    positions.set(node.id, {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    });
  });
  return positions;
}

export function gridLayout(
  nodes: GraphNode[],
  options: Partial<LayoutOptions> = {},
): PositionMap {
  const settings = optionsWithDefaults(options);
  const positions: PositionMap = new Map();
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  const spacing = settings.linkDistance + 30;
  nodes.forEach((node, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    positions.set(node.id, {
      x: (column - (columns - 1) / 2) * spacing,
      y: (row - (Math.ceil(nodes.length / columns) - 1) / 2) * spacing,
    });
  });
  return positions;
}

export function radialLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: Partial<LayoutOptions> = {},
): PositionMap {
  const settings = optionsWithDefaults(options);
  const links = adjacency(nodes, edges);
  const root = [...nodes].sort((a, b) => {
    const degree =
      (links.get(b.id)?.length ?? 0) - (links.get(a.id)?.length ?? 0);
    return degree || a.id - b.id;
  })[0];
  const positions: PositionMap = new Map();
  if (!root) return positions;
  positions.set(root.id, { x: 0, y: 0 });
  const visited = new Set([root.id]);
  let ring = [root.id];
  let depth = 1;
  while (ring.length) {
    const next: number[] = [];
    for (const id of ring) {
      for (const neighbor of links.get(id) ?? []) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        next.push(neighbor);
        const index = next.length - 1;
        const angle =
          (index * Math.PI * 2) / Math.max(1, next.length) + depth * 0.4;
        const radius = depth * settings.linkDistance;
        positions.set(neighbor, {
          x: Math.cos(angle) * radius,
          y: Math.sin(angle) * radius,
        });
      }
    }
    ring = next;
    depth += 1;
  }
  nodes.forEach((node) => {
    if (!positions.has(node.id)) {
      const point = spiralPoint(positions.size, settings.linkDistance / 2);
      positions.set(node.id, point);
    }
  });
  return positions;
}

export function treeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: Partial<LayoutOptions> = {},
): PositionMap {
  const settings = optionsWithDefaults(options);
  const links = adjacency(nodes, edges);
  const root = nodes.find((node) => node.kind === "folder") ?? nodes[0];
  const positions: PositionMap = new Map();
  if (!root) return positions;
  const levels = new Map<number, number[]>();
  const visited = new Set<number>([root.id]);
  let frontier = [root.id];
  let depth = 0;
  while (frontier.length) {
    levels.set(depth, frontier);
    const next: number[] = [];
    for (const id of frontier) {
      for (const neighbor of links.get(id) ?? []) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        next.push(neighbor);
      }
    }
    frontier = next;
    depth += 1;
  }
  for (const [level, ids] of levels) {
    ids.forEach((id, index) => {
      const spacing = settings.linkDistance + 40;
      positions.set(id, {
        x: (index - (ids.length - 1) / 2) * spacing,
        y: level * settings.linkDistance,
      });
    });
  }
  nodes.forEach((node) => {
    if (!positions.has(node.id)) {
      const point = spiralPoint(positions.size, settings.linkDistance / 3);
      positions.set(node.id, point);
    }
  });
  return positions;
}

export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  kind: LayoutKind,
  options: Partial<LayoutOptions> = {},
): PositionMap {
  switch (kind) {
    case "circle":
      return circleLayout(nodes, options);
    case "grid":
      return gridLayout(nodes, options);
    case "radial":
      return radialLayout(nodes, edges, options);
    case "tree":
      return treeLayout(nodes, edges, options);
    case "force":
      return forceLayout(nodes, edges, options);
  }
}

export function normalizePositions(
  positions: PositionMap,
  width: number,
  height: number,
): PositionMap {
  if (!positions.size) return new Map();
  const points = [...positions.values()];
  const middle = centroid(points);
  const offset = { x: width / 2 - middle.x, y: height / 2 - middle.y };
  const result: PositionMap = new Map();
  for (const [id, point] of positions) result.set(id, add(point, offset));
  return result;
}

export function mergePositions(
  base: PositionMap,
  extra: PositionMap,
): PositionMap {
  const merged = new Map(base);
  for (const [id, point] of extra) {
    if (!merged.has(id)) merged.set(id, point);
  }
  return merged;
}

export function clampPositions(
  positions: PositionMap,
  width: number,
  height: number,
): PositionMap {
  const result: PositionMap = new Map();
  for (const [id, point] of positions) {
    result.set(id, {
      x: Math.max(0, Math.min(width, point.x)),
      y: Math.max(0, Math.min(height, point.y)),
    });
  }
  return result;
}
