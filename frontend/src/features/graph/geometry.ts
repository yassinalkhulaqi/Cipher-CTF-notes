import type { Point, Rect, Size } from "./types";

export const EPSILON = 1e-6;

export function clamp(value: number, minimum: number, maximum: number): number {
  if (minimum > maximum) return minimum;
  return Math.min(maximum, Math.max(minimum, value));
}

export function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount;
}

export function smoothstep(amount: number): number {
  const value = clamp(amount, 0, 1);
  return value * value * (3 - 2 * value);
}

export function add(a: Point, b: Point): Point {
  return { x: a.x + b.x, y: a.y + b.y };
}

export function subtract(a: Point, b: Point): Point {
  return { x: a.x - b.x, y: a.y - b.y };
}

export function scale(point: Point, factor: number): Point {
  return { x: point.x * factor, y: point.y * factor };
}

export function length(vector: Point): number {
  return Math.hypot(vector.x, vector.y);
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function distanceSquared(a: Point, b: Point): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return dx * dx + dy * dy;
}

export function normalize(vector: Point): Point {
  const magnitude = length(vector);
  if (magnitude < EPSILON) return { x: 0, y: 0 };
  return { x: vector.x / magnitude, y: vector.y / magnitude };
}

export function rotate(vector: Point, radians: number): Point {
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return {
    x: vector.x * cosine - vector.y * sine,
    y: vector.x * sine + vector.y * cosine,
  };
}

export function midpoint(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

export function centroid(points: Point[]): Point {
  if (!points.length) return { x: 0, y: 0 };
  let x = 0;
  let y = 0;
  for (const point of points) {
    x += point.x;
    y += point.y;
  }
  return { x: x / points.length, y: y / points.length };
}

export function boundingBox(points: Point[]): Rect {
  if (!points.length) return { x: 0, y: 0, width: 0, height: 0 };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export function expandRect(rect: Rect, padding: number): Rect {
  return {
    x: rect.x - padding,
    y: rect.y - padding,
    width: rect.width + padding * 2,
    height: rect.height + padding * 2,
  };
}

export function unionRect(a: Rect, b: Rect): Rect {
  const minX = Math.min(a.x, b.x);
  const minY = Math.min(a.y, b.y);
  const maxX = Math.max(a.x + a.width, b.x + b.width);
  const maxY = Math.max(a.y + a.height, b.y + b.height);
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export function pointInRect(point: Point, rect: Rect): boolean {
  return (
    point.x >= rect.x &&
    point.x <= rect.x + rect.width &&
    point.y >= rect.y &&
    point.y <= rect.y + rect.height
  );
}

export function rectsIntersect(a: Rect, b: Rect): boolean {
  return !(
    a.x + a.width < b.x ||
    b.x + b.width < a.x ||
    a.y + a.height < b.y ||
    b.y + b.height < a.y
  );
}

export function clampPointToRect(point: Point, rect: Rect): Point {
  return {
    x: clamp(point.x, rect.x, rect.x + rect.width),
    y: clamp(point.y, rect.y, rect.y + rect.height),
  };
}

export function distanceToSegment(
  point: Point,
  start: Point,
  end: Point,
): number {
  const segment = subtract(end, start);
  const lengthSquared = segment.x * segment.x + segment.y * segment.y;
  if (lengthSquared < EPSILON) return distance(point, start);
  const projected =
    ((point.x - start.x) * segment.x + (point.y - start.y) * segment.y) /
    lengthSquared;
  const amount = clamp(projected, 0, 1);
  return distance(point, add(start, scale(segment, amount)));
}

export function segmentIntersection(
  a: Point,
  b: Point,
  c: Point,
  d: Point,
): Point | null {
  const r = subtract(b, a);
  const s = subtract(d, c);
  const denominator = r.x * s.y - r.y * s.x;
  if (Math.abs(denominator) < EPSILON) return null;
  const difference = subtract(c, a);
  const t = (difference.x * s.y - difference.y * s.x) / denominator;
  const u = (difference.x * r.y - difference.y * r.x) / denominator;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return add(a, scale(r, t));
}

export function segmentIntersectsRect(
  start: Point,
  end: Point,
  rect: Rect,
): boolean {
  if (pointInRect(start, rect) || pointInRect(end, rect)) return true;
  const topLeft = { x: rect.x, y: rect.y };
  const topRight = { x: rect.x + rect.width, y: rect.y };
  const bottomRight = { x: rect.x + rect.width, y: rect.y + rect.height };
  const bottomLeft = { x: rect.x, y: rect.y + rect.height };
  return [
    [topLeft, topRight],
    [topRight, bottomRight],
    [bottomRight, bottomLeft],
    [bottomLeft, topLeft],
  ].some(
    ([edgeStart, edgeEnd]) =>
      segmentIntersection(start, end, edgeStart, edgeEnd) !== null,
  );
}

export function fitScale(
  points: Point[],
  viewport: Size,
  padding = 24,
): number {
  if (!points.length) return 1;
  const box = expandRect(boundingBox(points), padding);
  if (box.width <= EPSILON || box.height <= EPSILON) return 1;
  return Math.min(viewport.width / box.width, viewport.height / box.height, 2);
}

export function centerOn(points: Point[], viewport: Size): Point {
  const box = boundingBox(points);
  return {
    x: viewport.width / 2 - (box.x + box.width / 2),
    y: viewport.height / 2 - (box.y + box.height / 2),
  };
}

export function quantize(value: number, step = 1): number {
  if (step <= 0) return value;
  return Math.round(value / step) * step;
}

export function spiralPoint(index: number, spacing = 32): Point {
  const angle = index * 2.399963229728653;
  const radius = spacing * Math.sqrt(index);
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export function damp(current: number, target: number, factor: number): number {
  return lerp(current, target, clamp(factor, 0, 1));
}
