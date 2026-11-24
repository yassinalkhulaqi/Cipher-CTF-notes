/** Pure geometry helpers shared by the canvas, minimap, and hit testing. */

import type { GraphEdge, GraphPayload, Point, Size, Viewport } from "./types";

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

export function distance(left: Point, right: Point): number {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

export function lerp(left: number, right: number, amount: number): number {
  return left + (right - left) * amount;
}

export function normalize(vector: Point): Point {
  const length = Math.hypot(vector.x, vector.y);
  if (length === 0) return { x: 0, y: 0 };
  return { x: vector.x / length, y: vector.y / length };
}

export function centroid(points: Point[]): Point {
  if (points.length === 0) return { x: 0, y: 0 };
  return {
    x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
    y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
  };
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
}

export function boundsOf(points: Point[]): Bounds {
  if (points.length === 0) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0, width: 0, height: 0 };
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return {
    minX,
    minY,
    maxX,
    maxY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

export function graphBounds(
  positions: Record<string, Point>,
  fallback: Size = { width: 1, height: 1 },
): Bounds {
  const points = Object.values(positions);
  if (points.length === 0) {
    return {
      minX: 0,
      minY: 0,
      maxX: fallback.width,
      maxY: fallback.height,
      width: fallback.width,
      height: fallback.height,
    };
  }
  return boundsOf(points);
}

export function fitScale(
  content: Bounds,
  viewport: Size,
  padding = 24,
): number {
  const availableWidth = Math.max(viewport.width - padding * 2, 1);
  const availableHeight = Math.max(viewport.height - padding * 2, 1);
  const scaleX = availableWidth / Math.max(content.width, 1);
  const scaleY = availableHeight / Math.max(content.height, 1);
  return clamp(Math.min(scaleX, scaleY), 0.05, 4);
}

export function identityViewport(): Viewport {
  return { x: 0, y: 0, width: 1200, height: 760, zoom: 1 };
}

export function worldToScreen(point: Point, viewport: Viewport): Point {
  return {
    x: (point.x - viewport.x) * viewport.zoom,
    y: (point.y - viewport.y) * viewport.zoom,
  };
}

export function screenToWorld(point: Point, viewport: Viewport): Point {
  return {
    x: point.x / viewport.zoom + viewport.x,
    y: point.y / viewport.zoom + viewport.y,
  };
}

export function panViewport(
  viewport: Viewport,
  dx: number,
  dy: number,
): Viewport {
  return {
    ...viewport,
    x: viewport.x - dx / viewport.zoom,
    y: viewport.y - dy / viewport.zoom,
  };
}

export function zoomAt(
  viewport: Viewport,
  point: Point,
  factor: number,
): Viewport {
  const before = screenToWorld(point, viewport);
  const zoom = clamp(viewport.zoom * factor, 0.1, 8);
  const next: Viewport = { ...viewport, zoom };
  const after = screenToWorld(point, next);
  return {
    ...next,
    x: next.x + before.x - after.x,
    y: next.y + before.y - after.y,
  };
}

export function fitViewport(
  positions: Record<string, Point>,
  viewport: Size,
): Viewport {
  const content = graphBounds(positions);
  const zoom = fitScale(content, viewport);
  return {
    x: content.minX - (viewport.width / zoom - content.width) / 2,
    y: content.minY - (viewport.height / zoom - content.height) / 2,
    width: viewport.width,
    height: viewport.height,
    zoom,
  };
}

export function constrainViewport(
  viewport: Viewport,
  content: Bounds,
): Viewport {
  const visibleWidth = viewport.width / viewport.zoom;
  const visibleHeight = viewport.height / viewport.zoom;
  const margin = 80;
  return {
    ...viewport,
    x: clamp(
      viewport.x,
      content.minX - margin - visibleWidth / 2,
      content.maxX + margin - visibleWidth / 2,
    ),
    y: clamp(
      viewport.y,
      content.minY - margin - visibleHeight / 2,
      content.maxY + margin - visibleHeight / 2,
    ),
  };
}

export function nearestNode(
  point: Point,
  positions: Record<string, Point>,
  radius = 22,
): string | null {
  let best: string | null = null;
  let bestDistance = radius;
  for (const id of Object.keys(positions).sort()) {
    const candidate = distance(point, positions[id]);
    if (candidate <= bestDistance) {
      best = id;
      bestDistance = candidate;
    }
  }
  return best;
}

export function pointToSegment(
  point: Point,
  left: Point,
  right: Point,
): number {
  const dx = right.x - left.x;
  const dy = right.y - left.y;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return distance(point, left);
  const amount = clamp(
    ((point.x - left.x) * dx + (point.y - left.y) * dy) / lengthSquared,
    0,
    1,
  );
  return distance(point, { x: left.x + dx * amount, y: left.y + dy * amount });
}

export function edgeKey(edge: GraphEdge): string {
  return `${edge.source}→${edge.target}:${edge.kind}`;
}

export function nearestEdge(
  point: Point,
  graph: GraphPayload,
  positions: Record<string, Point>,
  radius = 12,
): string | null {
  let best: string | null = null;
  let bestDistance = radius;
  for (const edge of graph.edges) {
    const left = positions[edge.source];
    const right = positions[edge.target];
    if (!left || !right) continue;
    const candidate = pointToSegment(point, left, right);
    if (candidate <= bestDistance) {
      best = edgeKey(edge);
      bestDistance = candidate;
    }
  }
  return best;
}

export function minimapRect(
  content: Bounds,
  size: Size,
  padding = 8,
): Viewport {
  const scale = fitScale(content, size, padding * 2);
  return {
    x: content.minX,
    y: content.minY,
    width: size.width,
    height: size.height,
    zoom: scale,
  };
}

export function roundPoint(point: Point, digits = 2): Point {
  const factor = 10 ** digits;
  return {
    x: Math.round(point.x * factor) / factor,
    y: Math.round(point.y * factor) / factor,
  };
}

export function smoothstep(amount: number): number {
  const t = clamp(amount, 0, 1);
  return t * t * (3 - 2 * t);
}
