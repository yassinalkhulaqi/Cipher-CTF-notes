/** SVG minimap with a draggable viewport rectangle. */

import type { MouseEvent } from "react";

import {
  minimapNodes,
  minimapToWorld,
  minimapTransform,
  viewportRect,
} from "./minimap";
import type { Rect } from "./minimap";
import type { Point, Size, Viewport } from "./types";

export interface WorkbenchMinimapProps {
  positions: Record<string, Point>;
  viewport: Viewport;
  size?: Size;
  colors?: Record<string, string>;
  kinds?: Record<string, string>;
  onNavigate?: (world: Point) => void;
}

export function WorkbenchMinimap({
  positions,
  viewport,
  size = { width: 220, height: 140 },
  colors = {},
  kinds = {},
  onNavigate,
}: WorkbenchMinimapProps) {
  const transform = minimapTransform(positions, size);
  const dots = minimapNodes(positions, transform);
  const rect: Rect = viewportRect(viewport, transform);
  const navigate = (event: MouseEvent<SVGSVGElement>) => {
    if (!onNavigate) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width === 0 || bounds.height === 0) return;
    const point = {
      x: ((event.clientX - bounds.left) / bounds.width) * size.width,
      y: ((event.clientY - bounds.top) / bounds.height) * size.height,
    };
    onNavigate(minimapToWorld(point, transform));
  };
  return (
    <div className="gw-minimap" data-testid="gw-minimap">
      <span className="gw-minimap__title">Minimap</span>
      <svg
        viewBox={`0 0 ${size.width} ${size.height}`}
        width={size.width}
        height={size.height}
        role="img"
        aria-label="Graph minimap; click to recenter"
        data-testid="gw-minimap-svg"
        onClick={navigate}
      >
        <rect
          x={0}
          y={0}
          width={size.width}
          height={size.height}
          className="gw-minimap__bg"
        />
        {dots.map((dot) => (
          <circle
            key={dot.id}
            cx={dot.point.x}
            cy={dot.point.y}
            r={2.4}
            fill={colors[kinds[dot.id] ?? ""] ?? "#38bdf8"}
            data-node={dot.id}
          />
        ))}
        <rect
          x={rect.x}
          y={rect.y}
          width={rect.width}
          height={rect.height}
          className="gw-minimap__viewport"
          data-testid="gw-minimap-viewport"
        />
      </svg>
    </div>
  );
}
