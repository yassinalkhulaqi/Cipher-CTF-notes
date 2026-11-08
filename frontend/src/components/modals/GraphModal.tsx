import { useEffect, useMemo, useRef, useState } from "react";
import { Network, Search } from "lucide-react";
import { api } from "../../lib/api";
import type { GraphNode, VaultGraph } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

interface Point {
  x: number;
  y: number;
}

const REST_LENGTH = 120;
const SETTLE_ALPHA = 0.02;
const MAX_STEPS = 340;

function initialPosition(seed: number): Point {
  const angle = seed * 2.399963 + 0.7;
  const radius = 40 + ((seed * 97) % 140);
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function shortTitle(title: string): string {
  const trimmed = title.trim();
  if (trimmed.length <= 20) return trimmed;
  return `${trimmed.slice(0, 19).trimEnd()}…`;
}

export function GraphModal() {
  const closeModal = useUiStore((state) => state.closeModal);
  const openNote = useAppStore((state) => state.openNote);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const toast = useUiStore((state) => state.toast);

  const [graph, setGraph] = useState<VaultGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const positionsRef = useRef<Map<number, Point>>(new Map());
  const frameRef = useRef<number | null>(null);
  const alphaRef = useRef(1);
  const [positions, setPositions] = useState<Map<number, Point>>(new Map());

  useEffect(() => {
    let cancelled = false;
    api
      .graph()
      .then((data) => {
        if (cancelled) return;
        positionsRef.current = new Map();
        setPositions(new Map());
        setGraph(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Could not load the vault graph",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const nodes = useMemo(() => graph?.nodes ?? [], [graph]);
  const folderCount = useMemo(
    () => nodes.filter((node) => node.kind === "folder").length,
    [nodes],
  );
  const danglingCount = useMemo(
    () => graph?.edges.filter((edge) => !edge.resolved).length ?? 0,
    [graph],
  );

  useEffect(() => {
    if (!graph) return;
    const positionsMap = positionsRef.current;
    for (const node of graph.nodes) {
      if (!positionsMap.has(node.id)) {
        positionsMap.set(node.id, initialPosition(positionsMap.size));
      }
    }
    let frame = 0;
    let alpha = alphaRef.current;

    const tick = () => {
      frame += 1;
      const current = positionsRef.current;
      const list = graph.nodes;
      if (list.length > 1) {
        const strength = 2400 * alpha;
        for (let i = 0; i < list.length; i += 1) {
          for (let j = i + 1; j < list.length; j += 1) {
            const a = current.get(list[i].id);
            const b = current.get(list[j].id);
            if (!a || !b) continue;
            const dx = a.x - b.x;
            const dy = a.y - b.y;
            const dist = Math.max(Math.hypot(dx, dy), 0.0001);
            const force = (strength * strength) / dist;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.x += fx * 0.02;
            a.y += fy * 0.02;
            b.x -= fx * 0.02;
            b.y -= fy * 0.02;
          }
        }
        for (const edge of graph.edges) {
          if (!edge.resolved) continue;
          const a = current.get(edge.source);
          const b = current.get(edge.target);
          if (!a || !b) continue;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.max(Math.hypot(dx, dy), 0.0001);
          const force = ((dist - REST_LENGTH) / dist) * 70 * alpha;
          a.x += dx * force;
          a.y += dy * force;
          b.x -= dx * force;
          b.y -= dy * force;
        }
        let centroidX = 0;
        let centroidY = 0;
        for (const node of list) {
          const point = current.get(node.id);
          if (point) {
            centroidX += point.x;
            centroidY += point.y;
          }
        }
        centroidX /= list.length;
        centroidY /= list.length;
        for (const node of list) {
          const point = current.get(node.id);
          if (!point) continue;
          point.x += (centroidX - point.x) * 0.012 * alpha;
          point.y += (centroidY - point.y) * 0.012 * alpha;
        }
      }
      alphaRef.current = alpha;
      alpha = Math.max(0, alpha - 0.006);
      setPositions(new Map(current));
      if (alpha > SETTLE_ALPHA && frame < MAX_STEPS) {
        frameRef.current = window.requestAnimationFrame(tick);
        return;
      }
      frameRef.current = null;
      alphaRef.current = 0;
      setPositions(new Map(current));
    };

    frameRef.current = window.requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null)
        window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [graph]);

  const visibleNodes = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = graph?.nodes ?? [];
    if (!needle) return list;
    return list.filter(
      (node) =>
        node.title.toLowerCase().includes(needle) ||
        node.path.toLowerCase().includes(needle),
    );
  }, [graph, query]);

  const visibleEdges = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map((node) => node.id));
    return (graph?.edges ?? []).filter(
      (edge) =>
        edge.resolved &&
        visibleIds.has(edge.source) &&
        visibleIds.has(edge.target),
    );
  }, [graph, visibleNodes]);

  const bounds = useMemo(() => {
    let minX = 0;
    let minY = 0;
    let maxX = 0;
    let maxY = 0;
    let found = false;
    for (const node of visibleNodes) {
      const point = positions.get(node.id);
      if (!point) continue;
      if (!found) {
        minX = point.x;
        minY = point.y;
        maxX = point.x;
        maxY = point.y;
        found = true;
        continue;
      }
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    }
    const width = Math.max(maxX - minX, 1) + 80;
    const height = Math.max(maxY - minY, 1) + 80;
    return { minX: minX - 40, minY: minY - 40, width, height };
  }, [visibleNodes, positions]);

  const open = (node: GraphNode) => {
    if (node.kind !== "note") return;
    closeModal();
    void openNote(node.id).catch((err: unknown) =>
      toast(
        err instanceof Error ? err.message : "Could not open note",
        "error",
      ),
    );
  };

  const notes = nodes.filter((node) => node.kind === "note").length;

  return (
    <Modal
      title="Vault graph"
      subtitle="Notes and the links between them"
      icon={<Network />}
      className="graph-modal"
      bodyClassName="graph-body"
      label="Vault graph"
      size="wide"
    >
      {error ? (
        <div className="graph-empty">
          <p>{error}</p>
          <button type="button" className="btn" onClick={closeModal}>
            Close
          </button>
        </div>
      ) : (
        <>
          <div className="graph-toolbar">
            <div className="sidebar-search graph-search">
              <Search />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter notes…"
                spellCheck={false}
                autoComplete="off"
                aria-label="Filter the vault graph"
              />
            </div>
            <span className="graph-meta">
              {notes} {notes === 1 ? "note" : "notes"} · {folderCount}{" "}
              {folderCount === 1 ? "folder" : "folders"}
              {danglingCount > 0 ? ` · ${danglingCount} unresolved` : ""}
            </span>
          </div>
          <div className="graph-canvas-wrap">
            {visibleNodes.length > 0 ? (
              <svg
                className="graph-canvas"
                viewBox={`0 0 ${bounds.width} ${bounds.height}`}
                role="img"
                aria-label="Vault knowledge graph"
              >
                {visibleEdges.map((edge) => {
                  const source = positions.get(edge.source);
                  const target = positions.get(edge.target);
                  if (!source || !target) return null;
                  return (
                    <line
                      key={`${edge.source}-${edge.target}-${edge.kind}`}
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      className={`graph-edge ${edge.kind === "parent" ? "parent" : "link"}`}
                    />
                  );
                })}
                {visibleNodes.map((node) => {
                  const point = positions.get(node.id);
                  if (!point) return null;
                  const isReference = node.kind === "reference";
                  return (
                    <g
                      key={node.id}
                      className={`graph-node ${isReference ? "reference" : ""}`}
                      onClick={() => open(node)}
                    >
                      <circle
                        cx={point.x}
                        cy={point.y}
                        r={isReference ? 9 : 14}
                        className="graph-disc"
                      />
                      <text
                        x={point.x}
                        y={point.y}
                        textAnchor="middle"
                        dominantBaseline="central"
                        className="graph-label"
                      >
                        {shortTitle(node.title)}
                      </text>
                      <title>{node.title}</title>
                    </g>
                  );
                })}
              </svg>
            ) : (
              <div className="graph-empty">
                <Network />
                <p>
                  {graph && graph.nodes.length === 0
                    ? "This vault has no notes yet."
                    : "No notes match the current filter."}
                </p>
                <button
                  type="button"
                  className="btn primary"
                  onClick={() => {
                    closeModal();
                    openNewNote();
                  }}
                >
                  Create a note
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
