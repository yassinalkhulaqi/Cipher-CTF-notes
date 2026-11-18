import { useEffect, useRef, useState } from "react";
import type {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";
import {
  hitTestEdge,
  hitTestNode,
  panViewport,
  zoomAt,
  drawGraph,
} from "./canvas";
import type { PositionMap } from "./layout";
import type {
  ClusterInfo,
  GraphEdge,
  GraphNode,
  Size,
  Viewport,
} from "./types";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  positions: PositionMap;
  clusters: ClusterInfo[];
  viewport: Viewport;
  selectedId: number | null;
  highlighted?: Set<number>;
  onViewportChange: (viewport: Viewport) => void;
  onSelect: (id: number | null) => void;
  onEdgeSelect?: (edge: GraphEdge | null) => void;
}

export function GraphCanvas({
  nodes,
  edges,
  positions,
  clusters,
  viewport,
  selectedId,
  highlighted,
  onViewportChange,
  onSelect,
  onEdgeSelect,
}: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [size, setSize] = useState<Size>({ width: 900, height: 620 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;
    const observer = new ResizeObserver(() => {
      setSize({
        width: parent.clientWidth || 900,
        height: parent.clientHeight || 620,
      });
    });
    observer.observe(parent);
    setSize({
      width: parent.clientWidth || 900,
      height: parent.clientHeight || 620,
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(size.width * ratio));
    canvas.height = Math.max(1, Math.floor(size.height * ratio));
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    drawGraph(ctx, {
      nodes,
      edges,
      positions,
      viewport,
      size,
      clusters,
      selectedId,
      highlighted,
    });
  }, [
    nodes,
    edges,
    positions,
    viewport,
    size,
    clusters,
    selectedId,
    highlighted,
  ]);

  const localPoint = (event: {
    currentTarget: HTMLCanvasElement;
    clientX: number;
    clientY: number;
  }) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const point = localPoint(event);
    dragRef.current = { x: point.x, y: point.y, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const point = localPoint(event);
    const dx = point.x - drag.x;
    const dy = point.y - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (drag.moved) onViewportChange(panViewport(viewport, dx, dy));
    drag.x = point.x;
    drag.y = point.y;
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag || drag.moved) return;
    const point = localPoint(event);
    const nodeId = hitTestNode(point, nodes, positions, viewport);
    if (nodeId !== null) {
      onSelect(nodeId);
      onEdgeSelect?.(null);
      return;
    }
    const edge = onEdgeSelect
      ? hitTestEdge(point, edges, positions, viewport)
      : null;
    onSelect(null);
    onEdgeSelect?.(edge);
  };

  const handleWheel = (event: ReactWheelEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    const point = localPoint(event);
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    onViewportChange(zoomAt(viewport, factor, point));
  };

  return (
    <div className="graph-canvas-host">
      <canvas
        ref={canvasRef}
        className="graph-canvas"
        aria-label="Vault graph canvas"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
        onWheel={handleWheel}
      />
    </div>
  );
}
