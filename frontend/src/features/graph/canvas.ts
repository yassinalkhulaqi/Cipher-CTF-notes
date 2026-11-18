import {
  pointInRect,
  distanceToSegment,
  fitScale,
  clamp,
  centerOn,
} from "./geometry";
import type { PositionMap } from "./layout";
import { clusterColorForNode } from "./clusters";
import type {
  ClusterInfo,
  GraphEdge,
  GraphNode,
  Point,
  Rect,
  Size,
  Viewport,
} from "./types";

export const MIN_SCALE = 0.2;
export const MAX_SCALE = 4;
export const NODE_RADIUS = 11;
export const LABEL_THRESHOLD = 0.65;

export function identityViewport(): Viewport {
  return { x: 0, y: 0, scale: 1 };
}

export function worldToScreen(point: Point, viewport: Viewport): Point {
  return {
    x: point.x * viewport.scale + viewport.x,
    y: point.y * viewport.scale + viewport.y,
  };
}

export function screenToWorld(point: Point, viewport: Viewport): Point {
  return {
    x: (point.x - viewport.x) / viewport.scale,
    y: (point.y - viewport.y) / viewport.scale,
  };
}

export function fitViewport(
  positions: PositionMap,
  size: Size,
  padding = 40,
): Viewport {
  const points = [...positions.values()];
  if (!points.length) return identityViewport();
  const scale = clamp(fitScale(points, size, padding), MIN_SCALE, MAX_SCALE);
  const center = centerOn(points, size);
  return { x: center.x * scale, y: center.y * scale, scale };
}

export function zoomAt(
  viewport: Viewport,
  factor: number,
  anchor: Point,
): Viewport {
  const scale = clamp(viewport.scale * factor, MIN_SCALE, MAX_SCALE);
  const world = screenToWorld(anchor, viewport);
  return {
    scale,
    x: anchor.x - world.x * scale,
    y: anchor.y - world.y * scale,
  };
}

export function panViewport(
  viewport: Viewport,
  dx: number,
  dy: number,
): Viewport {
  return { ...viewport, x: viewport.x + dx, y: viewport.y + dy };
}

export function nodeRect(point: Point, radius = NODE_RADIUS): Rect {
  return {
    x: point.x - radius,
    y: point.y - radius,
    width: radius * 2,
    height: radius * 2,
  };
}

export function hitTestNode(
  screenPoint: Point,
  nodes: GraphNode[],
  positions: PositionMap,
  viewport: Viewport,
  radius = NODE_RADIUS + 4,
): number | null {
  let best: number | null = null;
  let bestDistance = Infinity;
  for (const node of nodes) {
    const world = positions.get(node.id);
    if (!world) continue;
    const point = worldToScreen(world, viewport);
    const current = Math.hypot(
      point.x - screenPoint.x,
      point.y - screenPoint.y,
    );
    if (current <= radius && current < bestDistance) {
      bestDistance = current;
      best = node.id;
    }
  }
  return best;
}

export function hitTestEdge(
  screenPoint: Point,
  edges: GraphEdge[],
  positions: PositionMap,
  viewport: Viewport,
  tolerance = 6,
): GraphEdge | null {
  let best: GraphEdge | null = null;
  let bestDistance = tolerance;
  for (const edge of edges) {
    const start = positions.get(edge.source);
    const end = positions.get(edge.target);
    if (!start || !end) continue;
    const distance = distanceToSegment(
      screenPoint,
      worldToScreen(start, viewport),
      worldToScreen(end, viewport),
    );
    if (distance <= bestDistance) {
      bestDistance = distance;
      best = edge;
    }
  }
  return best;
}

export function visibleNodeIds(
  positions: PositionMap,
  viewport: Viewport,
  size: Size,
  margin = 40,
): Set<number> {
  const bounds: Rect = {
    x: -margin,
    y: -margin,
    width: size.width + margin * 2,
    height: size.height + margin * 2,
  };
  const result = new Set<number>();
  for (const [id, point] of positions) {
    if (pointInRect(worldToScreen(point, viewport), bounds)) result.add(id);
  }
  return result;
}

export function lodLevel(scale: number): "low" | "medium" | "high" {
  if (scale < 0.45) return "low";
  if (scale < 1.2) return "medium";
  return "high";
}

export function shouldDrawLabels(scale: number): boolean {
  return scale >= LABEL_THRESHOLD;
}

export interface DrawGraphOptions {
  nodes: GraphNode[];
  edges: GraphEdge[];
  positions: PositionMap;
  viewport: Viewport;
  size: Size;
  clusters?: ClusterInfo[];
  selectedId?: number | null;
  highlighted?: Set<number>;
  showLabels?: boolean;
}

export function clearCanvas(ctx: CanvasRenderingContext2D, size: Size): void {
  ctx.clearRect(0, 0, size.width, size.height);
}

export function drawEdge(
  ctx: CanvasRenderingContext2D,
  edge: GraphEdge,
  positions: PositionMap,
  viewport: Viewport,
  color: string,
): void {
  const start = positions.get(edge.source);
  const end = positions.get(edge.target);
  if (!start || !end) return;
  const from = worldToScreen(start, viewport);
  const to = worldToScreen(end, viewport);
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.strokeStyle = edge.resolved === false ? `${color}66` : color;
  ctx.lineWidth =
    edge.resolved === false ? 1 : Math.max(0.8, Math.min(3, edge.weight ?? 1));
  ctx.setLineDash(edge.resolved === false ? [4, 4] : []);
  ctx.stroke();
  ctx.setLineDash([]);
}

export function drawNode(
  ctx: CanvasRenderingContext2D,
  node: GraphNode,
  point: Point,
  color: string,
  selected: boolean,
  showLabel: boolean,
): void {
  const radius = selected ? NODE_RADIUS + 3 : NODE_RADIUS;
  ctx.beginPath();
  ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = selected ? 3 : 1;
  ctx.strokeStyle = selected ? "#f8fafc" : "#0f172a";
  ctx.stroke();
  if (showLabel) {
    ctx.font = "12px system-ui, sans-serif";
    ctx.fillStyle = "#e2e8f0";
    ctx.fillText(node.label, point.x + radius + 6, point.y + 4);
  }
}

export function drawGraph(
  ctx: CanvasRenderingContext2D,
  options: DrawGraphOptions,
): void {
  const {
    nodes,
    edges,
    positions,
    viewport,
    size,
    clusters = [],
    selectedId = null,
    highlighted,
    showLabels = shouldDrawLabels(viewport.scale),
  } = options;
  clearCanvas(ctx, size);
  const visible = visibleNodeIds(positions, viewport, size);
  const level = lodLevel(viewport.scale);
  for (const edge of edges) {
    if (!visible.has(edge.source) || !visible.has(edge.target)) continue;
    const emphasis =
      highlighted?.has(edge.source) && highlighted.has(edge.target);
    const color = emphasis
      ? "#facc15"
      : edge.kind === "tag"
        ? "#64748b"
        : "#475569";
    drawEdge(ctx, edge, positions, viewport, color);
  }
  for (const node of nodes) {
    if (!visible.has(node.id)) continue;
    const world = positions.get(node.id);
    if (!world) continue;
    const point = worldToScreen(world, viewport);
    const color =
      node.kind === "reference"
        ? "#f87171"
        : node.kind === "tag"
          ? "#a78bfa"
          : clusterColorForNode(clusters, node.id);
    const selected = node.id === selectedId;
    const dimmed =
      highlighted !== undefined && !highlighted.has(node.id) && !selected;
    ctx.globalAlpha = dimmed ? 0.35 : 1;
    drawNode(ctx, node, point, color, selected, showLabels && level !== "low");
    ctx.globalAlpha = 1;
  }
}

export function screenCenter(size: Size): Point {
  return { x: size.width / 2, y: size.height / 2 };
}
