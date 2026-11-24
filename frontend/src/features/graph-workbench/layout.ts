/** Deterministic layout strategies mirrored from the Python workbench. */

import type {
  GraphPayload,
  LayoutKind,
  LayoutOptions,
  LayoutResult,
  Point,
} from "./types";

export class SeededRandom {
  private state: number;
  readonly seed: number;

  constructor(seed = 1) {
    this.seed = Math.trunc(seed);
    this.state = this.seed >>> 0 || 0x9e3779b9;
  }

  nextU32(): number {
    let value = this.state >>> 0;
    value ^= value << 13;
    value >>>= 0;
    value ^= value >>> 17;
    value ^= value << 5;
    this.state = value >>> 0;
    return this.state;
  }

  random(): number {
    return this.nextU32() / 0x100000000;
  }

  between(low: number, high: number): number {
    return low + (high - low) * this.random();
  }

  below(count: number): number {
    return count <= 0 ? 0 : this.nextU32() % count;
  }

  shuffle<T>(items: T[]): T[] {
    const result = items.slice();
    for (let index = result.length - 1; index > 0; index -= 1) {
      const other = this.below(index + 1);
      [result[index], result[other]] = [result[other], result[index]];
    }
    return result;
  }
}

export function stableHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

export function createRandom(seed: number): SeededRandom {
  return new SeededRandom(seed);
}

function nodeIds(graph: GraphPayload): string[] {
  return graph.nodes.map((node) => node.id).sort();
}

function innerBox(options: LayoutOptions) {
  const left = Math.min(options.padding, options.width / 3);
  const top = Math.min(options.padding, options.height / 3);
  return {
    left,
    top,
    right: options.width - left,
    bottom: options.height - top,
  };
}

export function normalizePositions(
  points: Record<string, Point>,
  options: LayoutOptions,
): Record<string, Point> {
  const entries = Object.entries(points);
  if (entries.length === 0) return {};
  const xs = entries.map(([, point]) => point.x);
  const ys = entries.map(([, point]) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const box = innerBox(options);
  const scale = Math.min(
    Math.max(box.right - box.left, 1) / spanX,
    Math.max(box.bottom - box.top, 1) / spanY,
  );
  const offsetX = box.left + (box.right - box.left - spanX * scale) / 2;
  const offsetY = box.top + (box.bottom - box.top - spanY * scale) / 2;
  const result: Record<string, Point> = {};
  for (const [id, point] of entries) {
    result[id] = {
      x: Math.round((offsetX + (point.x - minX) * scale) * 100) / 100,
      y: Math.round((offsetY + (point.y - minY) * scale) * 100) / 100,
    };
  }
  return result;
}

function degreeMap(graph: GraphPayload): Record<string, number> {
  const degrees: Record<string, number> = {};
  for (const node of graph.nodes) degrees[node.id] = 0;
  for (const edge of graph.edges) {
    if (degrees[edge.source] !== undefined) degrees[edge.source] += 1;
    if (degrees[edge.target] !== undefined) degrees[edge.target] += 1;
  }
  return degrees;
}

export function hubOf(graph: GraphPayload): string {
  const degrees = degreeMap(graph);
  return (
    Object.keys(degrees).sort(
      (a, b) => degrees[b] - degrees[a] || a.localeCompare(b),
    )[0] ?? ""
  );
}

function iterationBudget(size: number, requested: number): number {
  if (size <= 400) return requested;
  return Math.max(
    6,
    Math.min(requested, Math.floor(12000 / Math.max(size / 10, 1))),
  );
}

function initialPoints(
  ids: string[],
  rng: SeededRandom,
): Record<string, Point> {
  const points: Record<string, Point> = {};
  ids.forEach((id, index) => {
    const angle = index * 2.399963229728653 + (stableHash(id) % 1000) / 1000;
    const radius = 0.35 * Math.sqrt(index + 1) + rng.between(-0.05, 0.05);
    points[id] = { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
  });
  return points;
}

function peers(
  ids: string[],
  index: number,
  sample: number,
  step: number,
): string[] {
  const size = ids.length;
  const stride = Math.max(1, Math.floor(size / Math.max(sample - 1, 1)));
  const start = (index + step * stride) % size;
  const result: string[] = [];
  for (let offset = 0; offset < sample - 1; offset += 1) {
    result.push(ids[(start + offset * stride) % size]);
  }
  return result;
}

export function forceLayout(
  graph: GraphPayload,
  options: LayoutOptions,
): Record<string, Point> {
  const ids = nodeIds(graph);
  if (ids.length === 0) return {};
  const rng = createRandom(options.seed);
  let points = initialPoints(ids, rng);
  const edges = graph.edges
    .filter((edge) => points[edge.source] && points[edge.target])
    .map((edge) => ({
      source: edge.source,
      target: edge.target,
      weight: Math.max(edge.weight, 0.05),
    }));
  const sample = Math.min(options.sampleSize, Math.max(2, ids.length));
  const iterations = iterationBudget(ids.length, options.iterations);
  for (let step = 0; step < iterations; step += 1) {
    const cooling = 1 / (1 + step * 0.12);
    const next: Record<string, Point> = {};
    for (let index = 0; index < ids.length; index += 1) {
      const id = ids[index];
      const current = points[id];
      let pushX = -current.x * 0.01;
      let pushY = -current.y * 0.01;
      for (const otherId of peers(ids, index, sample, step)) {
        if (otherId === id) continue;
        const other = points[otherId];
        const diffX = current.x - other.x;
        const diffY = current.y - other.y;
        const squared = diffX * diffX + diffY * diffY + 0.02;
        const strength = 0.9 / squared;
        const length = Math.sqrt(squared);
        pushX += (strength * diffX) / length;
        pushY += (strength * diffY) / length;
      }
      for (const edge of edges) {
        if (edge.source !== id && edge.target !== id) continue;
        const other = points[edge.source === id ? edge.target : edge.source];
        const diffX = other.x - current.x;
        const diffY = other.y - current.y;
        const length = Math.hypot(diffX, diffY) + 0.01;
        const strength = Math.min(length - 1.4, 1.2) * edge.weight * 0.08;
        pushX += (strength * diffX) / length;
        pushY += (strength * diffY) / length;
      }
      next[id] = {
        x: Math.max(-50, Math.min(50, current.x + pushX * cooling)),
        y: Math.max(-50, Math.min(50, current.y + pushY * cooling)),
      };
    }
    points = next;
  }
  return points;
}

function layersOf(graph: GraphPayload, root: string): string[][] {
  const ids = nodeIds(graph);
  const incoming: Record<string, number> = {};
  const outgoing: Record<string, string[]> = {};
  for (const id of ids) {
    incoming[id] = 0;
    outgoing[id] = [];
  }
  for (const edge of graph.edges) {
    if (edge.source === edge.target) continue;
    if (
      incoming[edge.source] === undefined ||
      incoming[edge.target] === undefined
    )
      continue;
    outgoing[edge.source].push(edge.target);
    incoming[edge.target] += 1;
  }
  const degrees = degreeMap(graph);
  let roots = ids.filter((id) => incoming[id] === 0);
  if (root && incoming[root] !== undefined) roots = [root];
  if (roots.length === 0) {
    roots = [
      ids
        .slice()
        .sort((a, b) => degrees[b] - degrees[a] || a.localeCompare(b))[0],
    ];
  }
  const depth: Record<string, number> = {};
  const queue: Array<[string, number]> = roots.sort().map((id) => [id, 0]);
  let cursor = 0;
  while (cursor < queue.length) {
    const [id, level] = queue[cursor];
    cursor += 1;
    if (depth[id] !== undefined && depth[id] <= level) continue;
    depth[id] = level;
    for (const target of outgoing[id].slice().sort()) {
      if (level + 1 <= ids.length) queue.push([target, level + 1]);
    }
  }
  for (const id of ids) if (depth[id] === undefined) depth[id] = 0;
  const maxDepth = Math.max(...Object.values(depth));
  const groups: string[][] = Array.from({ length: maxDepth + 1 }, () => []);
  const ordered = ids.slice().sort((a, b) => {
    const byDepth = depth[a] - depth[b];
    return byDepth || degrees[b] - degrees[a] || a.localeCompare(b);
  });
  for (const id of ordered) groups[depth[id]].push(id);
  return groups.filter((group) => group.length > 0);
}

export function hierarchicalLayout(
  graph: GraphPayload,
  options: LayoutOptions,
): Record<string, Point> {
  const layers = layersOf(graph, options.root);
  const points: Record<string, Point> = {};
  layers.forEach((layer, layerIndex) => {
    layer.forEach((id, position) => {
      const across = (position + 1) / (layer.length + 1);
      const depth = layerIndex / Math.max(layers.length - 1, 1);
      points[id] =
        options.direction === "TB"
          ? { x: across, y: depth }
          : { x: depth, y: across };
    });
  });
  return points;
}

function ringsOf(graph: GraphPayload, center: string): Record<string, number> {
  const adjacency: Record<string, string[]> = {};
  for (const node of graph.nodes) adjacency[node.id] = [];
  for (const edge of graph.edges) {
    if (
      adjacency[edge.source] === undefined ||
      adjacency[edge.target] === undefined
    )
      continue;
    adjacency[edge.source].push(edge.target);
    adjacency[edge.target].push(edge.source);
  }
  const result: Record<string, number> = { [center]: 0 };
  let frontier = [center];
  let depth = 0;
  while (frontier.length > 0) {
    const following: string[] = [];
    for (const id of frontier) {
      for (const neighbor of adjacency[id]) {
        if (result[neighbor] !== undefined) continue;
        result[neighbor] = depth + 1;
        following.push(neighbor);
      }
    }
    frontier = following.sort();
    depth += 1;
  }
  return result;
}

export function radialLayout(
  graph: GraphPayload,
  options: LayoutOptions,
): Record<string, Point> {
  const ids = nodeIds(graph);
  if (ids.length === 0) return {};
  const center =
    options.root && graph.nodes.some((node) => node.id === options.root)
      ? options.root
      : hubOf(graph);
  const rings = ringsOf(graph, center);
  const maxRing = Math.max(...Object.values(rings), 0);
  const kinds: Record<string, string> = {};
  for (const node of graph.nodes) kinds[node.id] = node.kind;
  const points: Record<string, Point> = {};
  for (let ring = 0; ring <= maxRing; ring += 1) {
    const members = Object.keys(rings)
      .filter((id) => rings[id] === ring)
      .sort(
        (a, b) =>
          (kinds[a] ?? "").localeCompare(kinds[b] ?? "") || a.localeCompare(b),
      );
    const radius = 0.12 + 0.38 * (ring / Math.max(maxRing, 1));
    members.forEach((id, index) => {
      const angle =
        (2 * Math.PI * index) / Math.max(members.length, 1) + ring * 0.31;
      points[id] = {
        x: 0.5 + Math.cos(angle) * radius,
        y: 0.5 + Math.sin(angle) * radius,
      };
    });
  }
  return points;
}

function timeOf(graph: GraphPayload, id: string, key: string): number {
  const node = graph.nodes.find((item) => item.id === id);
  if (!node) return 0;
  if (key === "timestamp") return node.timestamp;
  const value = node.metadata[key];
  if (typeof value === "number") return value;
  if (typeof value === "string") return (stableHash(value) % 100000) / 100000;
  return 0;
}

export function timelineLayout(
  graph: GraphPayload,
  options: LayoutOptions,
): Record<string, Point> {
  const ids = nodeIds(graph).sort(
    (a, b) =>
      timeOf(graph, a, options.timeKey) - timeOf(graph, b, options.timeKey) ||
      a.localeCompare(b),
  );
  const kinds = Array.from(
    new Set(graph.nodes.map((node) => node.kind)),
  ).sort();
  const lanes: Record<string, number> = {};
  kinds.forEach((kind, index) => {
    lanes[kind] = index;
  });
  const points: Record<string, Point> = {};
  ids.forEach((id, index) => {
    const node = graph.nodes.find((item) => item.id === id);
    const lane = lanes[node?.kind ?? ""] ?? kinds.length;
    points[id] = {
      x: (index + 1) / (ids.length + 1),
      y: lane / Math.max(kinds.length, 1),
    };
  });
  return points;
}

export function computeLayout(
  graph: GraphPayload,
  strategy: LayoutKind,
  options: LayoutOptions,
): LayoutResult {
  const raw =
    strategy === "force"
      ? forceLayout(graph, options)
      : strategy === "hierarchical"
        ? hierarchicalLayout(graph, options)
        : strategy === "radial"
          ? radialLayout(graph, options)
          : timelineLayout(graph, options);
  return {
    strategy,
    seed: options.seed,
    width: options.width,
    height: options.height,
    center: options.root || hubOf(graph),
    positions: normalizePositions(raw, options),
  };
}

export function layoutSignature(result: LayoutResult): string {
  return Object.keys(result.positions)
    .sort()
    .map((id) => {
      const point = result.positions[id];
      return `${id}:${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    })
    .join("|");
}
