/** Minimap projection and viewport helpers for the graph workbench. */

import { boundsOf, clamp, graphBounds, roundPoint } from "./geometry";
import type { Bounds } from "./geometry";
import type { Point, Size, Viewport } from "./types";

export interface MinimapTransform {
  scale: number;
  offsetX: number;
  offsetY: number;
  content: Bounds;
  size: Size;
}

export function minimapTransform(
  positions: Record<string, Point>,
  size: Size,
  padding = 12,
): MinimapTransform {
  const content = graphBounds(positions);
  const scale = Math.min(
    Math.max(size.width - padding * 2, 1) / Math.max(content.width, 1),
    Math.max(size.height - padding * 2, 1) / Math.max(content.height, 1),
  );
  return {
    scale,
    offsetX: padding + (size.width - padding * 2 - content.width * scale) / 2,
    offsetY: padding + (size.height - padding * 2 - content.height * scale) / 2,
    content,
    size,
  };
}

export function projectToMinimap(
  point: Point,
  transform: MinimapTransform,
): Point {
  return roundPoint(
    {
      x:
        transform.offsetX +
        (point.x - transform.content.minX) * transform.scale,
      y:
        transform.offsetY +
        (point.y - transform.content.minY) * transform.scale,
    },
    2,
  );
}

export function minimapNodes(
  positions: Record<string, Point>,
  transform: MinimapTransform,
): Array<{ id: string; point: Point }> {
  return Object.keys(positions)
    .sort()
    .map((id) => ({ id, point: projectToMinimap(positions[id], transform) }));
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function viewportRect(
  viewport: Viewport,
  transform: MinimapTransform,
): Rect {
  const width = Math.max(1, (viewport.width / viewport.zoom) * transform.scale);
  const height = Math.max(
    1,
    (viewport.height / viewport.zoom) * transform.scale,
  );
  const topLeft = projectToMinimap({ x: viewport.x, y: viewport.y }, transform);
  return {
    x: roundPoint(topLeft, 2).x,
    y: roundPoint(topLeft, 2).y,
    width: roundPoint({ x: width, y: 0 }, 2).x,
    height: roundPoint({ x: 0, y: height }, 2).y,
  };
}

export function minimapToWorld(
  point: Point,
  transform: MinimapTransform,
): Point {
  return {
    x: transform.content.minX + (point.x - transform.offsetX) / transform.scale,
    y: transform.content.minY + (point.y - transform.offsetY) / transform.scale,
  };
}

export function centerViewportAt(
  viewport: Viewport,
  world: Point,
  graphSize: Size,
): Viewport {
  return {
    ...viewport,
    x: clamp(
      world.x - viewport.width / (2 * viewport.zoom),
      graphSize.width * -1,
      graphSize.width * 2,
    ),
    y: clamp(
      world.y - viewport.height / (2 * viewport.zoom),
      graphSize.height * -1,
      graphSize.height * 2,
    ),
  };
}

export function minimapCoverage(rect: Rect, size: Size): number {
  const area = rect.width * rect.height;
  const total = size.width * size.height;
  if (total <= 0) return 0;
  return clamp(area / total, 0, 1);
}

export function clusterDots(
  centroids: Record<string, Point>,
  transform: MinimapTransform,
): Array<{ key: string; point: Point }> {
  return Object.keys(centroids)
    .sort()
    .map((key) => ({
      key,
      point: projectToMinimap(centroids[key], transform),
    }));
}

export function minimapBounds(positions: Record<string, Point>): Bounds {
  return boundsOf(Object.values(positions));
}
