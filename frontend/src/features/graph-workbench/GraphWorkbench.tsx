/** Main graph workbench feature surface. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { shortestPath, structuralSummary } from "./analysis";
import { buildClusters, clusterChips, filterByCluster } from "./clusters";
import { GraphWorkbenchClient } from "./client";
import {
  applyLocalEdge,
  cancelGesture,
  commitGesture,
  draftToEdge,
  historySummary,
  initialGesture,
  initialHistory,
  pushEdit,
  redoEdit,
  removeLocalEdge,
  selectNode,
  setGestureKind,
  setGestureLabel,
  setGestureWeight,
  undoEdit,
  validateDraft,
} from "./editor";
import {
  edgeKey,
  fitViewport,
  identityViewport,
  panViewport,
  zoomAt,
} from "./geometry";
import { computeLayout } from "./layout";
import { ClusterChips } from "./ClusterChips";
import { LayoutSwitcher } from "./LayoutSwitcher";
import { PathExplorer } from "./PathExplorer";
import { RelationshipPanel } from "./RelationshipPanel";
import { WorkbenchInspector } from "./WorkbenchInspector";
import { WorkbenchMinimap } from "./WorkbenchMinimap";
import { buildInspector, formatTimestamp } from "./inspector";
import type {
  ClusterDimension,
  EditRecord,
  GraphPayload,
  LayoutKind,
  LayoutOptions,
  PathResult,
  Viewport,
} from "./types";
import {
  DEFAULT_LAYOUT_OPTIONS,
  KIND_COLORS,
  layoutOptionsFrom,
} from "./types";

export interface GraphWorkbenchProps {
  client?: GraphWorkbenchClient;
  initialGraph?: GraphPayload;
  density?: "comfortable" | "compact";
  onNotice?: (message: string) => void;
  onExport?: (content: string, format: string) => void;
}

const EMPTY_GRAPH: GraphPayload = { nodes: [], edges: [] };

export function GraphWorkbench({
  client,
  initialGraph,
  density = "comfortable",
  onNotice,
  onExport,
}: GraphWorkbenchProps) {
  const [graph, setGraph] = useState<GraphPayload>(initialGraph ?? EMPTY_GRAPH);
  const [layoutKind, setLayoutKind] = useState<LayoutKind>("force");
  const [options, setOptions] = useState<LayoutOptions>(DEFAULT_LAYOUT_OPTIONS);
  const [dimension, setDimension] = useState<ClusterDimension>("tag");
  const [selectedCluster, setSelectedCluster] = useState("");
  const [selectedNode, setSelectedNode] = useState("");
  const [hoveredNode, setHoveredNode] = useState("");
  const [gesture, setGesture] = useState(initialGesture());
  const [history, setHistory] = useState(initialHistory());
  const [lastRecord, setLastRecord] = useState<EditRecord | null>(null);
  const [pathSource, setPathSource] = useState("");
  const [pathTarget, setPathTarget] = useState("");
  const [pathResult, setPathResult] = useState<PathResult | null>(null);
  const [viewport, setViewport] = useState<Viewport>(identityViewport());
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const drag = useRef<{ x: number; y: number; viewport: Viewport } | null>(
    null,
  );

  const notify = useCallback(
    (message: string) => {
      setNotice(message);
      onNotice?.(message);
    },
    [onNotice],
  );

  useEffect(() => {
    if (!client || initialGraph) return;
    let cancelled = false;
    setBusy(true);
    client
      .graph()
      .then((payload) => {
        if (!cancelled && payload) setGraph(payload);
      })
      .catch((error: unknown) =>
        notify(error instanceof Error ? error.message : String(error)),
      )
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, initialGraph, notify]);

  const layoutResult = useMemo(
    () => computeLayout(graph, layoutKind, options),
    [graph, layoutKind, options],
  );
  const positions = layoutResult.positions;
  const clusters = useMemo(
    () => buildClusters(graph, dimension),
    [graph, dimension],
  );
  const chips = useMemo(
    () => clusterChips(clusters, selectedCluster),
    [clusters, selectedCluster],
  );
  const visibleGraph = useMemo(
    () => filterByCluster(graph, clusters, selectedCluster),
    [graph, clusters, selectedCluster],
  );
  const visibleIds = useMemo(
    () => new Set(visibleGraph.nodes.map((node) => node.id)),
    [visibleGraph],
  );
  const structure = useMemo(
    () => (graph.nodes.length <= 1500 ? structuralSummary(graph) : null),
    [graph],
  );
  const inspector = useMemo(() => {
    const node = graph.nodes.find((item) => item.id === selectedNode);
    if (!node) return null;
    return buildInspector(node, undefined, {
      degree: graph.edges.filter(
        (edge) => edge.source === node.id || edge.target === node.id,
      ).length,
      neighbors: graph.edges
        .filter((edge) => edge.source === node.id || edge.target === node.id)
        .map((edge) => {
          const id = edge.source === node.id ? edge.target : edge.source;
          return {
            id,
            label: graph.nodes.find((item) => item.id === id)?.label ?? id,
          };
        }),
      clusters: Object.fromEntries(
        ["tag", "kind", "severity"].map((item) => [
          item,
          buildClusters(graph, item as ClusterDimension).assignments[node.id] ??
            "",
        ]),
      ),
    });
  }, [graph, selectedNode]);

  const kinds = useMemo(() => {
    const result: Record<string, string> = {};
    for (const node of graph.nodes) result[node.id] = node.kind;
    return result;
  }, [graph]);

  const focusNode = useCallback(
    (id: string) => {
      setSelectedNode(id);
      if (!pathSource) {
        setPathSource(id);
      } else if (!pathTarget && pathSource !== id) {
        setPathTarget(id);
      }
    },
    [pathSource, pathTarget],
  );

  const handleNodeClick = useCallback(
    (id: string) => {
      if (gesture.phase !== "idle") {
        setGesture(selectNode(gesture, id));
      } else {
        focusNode(id);
      }
    },
    [gesture, focusNode],
  );

  const handleCommit = useCallback(async () => {
    const problems = validateDraft(gesture.draft, graph);
    if (problems.length > 0) {
      notify(problems.join(" "));
      return;
    }
    const edge = draftToEdge(gesture.draft);
    if (client) {
      setBusy(true);
      try {
        await client.connect(gesture.draft);
      } catch (error) {
        notify(error instanceof Error ? error.message : String(error));
        return;
      } finally {
        setBusy(false);
      }
    }
    setGraph((previous) => applyLocalEdge(previous, edge));
    const next = pushEdit(history, {
      action: "add",
      link: edge,
      inverse: {},
      timestamp: Date.now() / 1000,
      actor: "local",
    });
    setHistory(next);
    setLastRecord(next.undo[next.undo.length - 1] ?? null);
    setGesture(commitGesture(gesture));
    notify(`Connected ${edge.source} to ${edge.target}.`);
  }, [gesture, graph, client, history, notify]);

  const handleUndo = useCallback(async () => {
    if (client) {
      try {
        await client.undo();
      } catch (error) {
        notify(error instanceof Error ? error.message : String(error));
        return;
      }
    }
    const result = undoEdit(history);
    const record = result.record;
    if (!record) return;
    setGraph((previous) =>
      record.action === "add"
        ? removeLocalEdge(previous, record.link)
        : applyLocalEdge(previous, record.link),
    );
    setHistory(result.history);
    setLastRecord(record);
    notify(`Undid ${record.action}.`);
  }, [client, history, notify]);

  const handleRedo = useCallback(async () => {
    if (client) {
      try {
        await client.redo();
      } catch (error) {
        notify(error instanceof Error ? error.message : String(error));
        return;
      }
    }
    const result = redoEdit(history);
    const record = result.record;
    if (!record) return;
    setGraph((previous) =>
      record.action === "add"
        ? applyLocalEdge(previous, record.link)
        : removeLocalEdge(previous, record.link),
    );
    setHistory(result.history);
    setLastRecord(record);
    notify(`Redid ${record.action}.`);
  }, [client, history, notify]);

  const handleFindPath = useCallback(async () => {
    if (!pathSource || !pathTarget) {
      notify("Choose both path endpoints.");
      return;
    }
    if (client) {
      setBusy(true);
      try {
        const result = await client.path(pathSource, pathTarget);
        setPathResult(result);
        notify(
          result.found
            ? `Path explored in ${result.hops} hop(s).`
            : "No path found.",
        );
        return;
      } catch (error) {
        notify(error instanceof Error ? error.message : String(error));
        return;
      } finally {
        setBusy(false);
      }
    }
    const result = shortestPath(graph, pathSource, pathTarget);
    setPathResult(result);
    notify(
      result.found
        ? `Path explored in ${result.hops} hop(s).`
        : "No path found.",
    );
  }, [client, graph, pathSource, pathTarget, notify]);

  const handleSnapshot = useCallback(async () => {
    if (!client) {
      notify("A V3 client is required to store snapshots.");
      return;
    }
    try {
      const snapshot = await client.capture("Workbench capture");
      notify(`Snapshot ${snapshot.meta.id} stored.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error));
    }
  }, [client, notify]);

  const handleExport = useCallback(
    async (format: "json" | "dot" | "mermaid") => {
      if (!client) {
        notify("A V3 client is required to export graphs.");
        return;
      }
      try {
        const result = await client.exportGraph(format);
        onExport?.(result.content, format);
        notify(`Exported ${result.content.length} characters of ${format}.`);
      } catch (error) {
        notify(error instanceof Error ? error.message : String(error));
      }
    },
    [client, notify, onExport],
  );

  const canvasPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: event.clientX, y: event.clientY, viewport };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const canvasPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width === 0 || bounds.height === 0) return;
    const dx =
      ((event.clientX - drag.current.x) * options.width) / bounds.width;
    const dy =
      ((event.clientY - drag.current.y) * options.height) / bounds.height;
    setViewport(panViewport(drag.current.viewport, dx, dy));
  };
  const canvasPointerUp = () => {
    drag.current = null;
  };
  const canvasWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width === 0 || bounds.height === 0) return;
    const point = {
      x: ((event.clientX - bounds.left) * options.width) / bounds.width,
      y: ((event.clientY - bounds.top) * options.height) / bounds.height,
    };
    setViewport((current) =>
      zoomAt(current, point, event.deltaY < 0 ? 1.1 : 0.9),
    );
  };

  const transform = `translate(${-viewport.x * viewport.zoom} ${-viewport.y * viewport.zoom}) scale(${viewport.zoom})`;

  return (
    <div className="gw-root" data-density={density} data-testid="gw-root">
      <V3Panel
        title="Graph workbench"
        subtitle="Layout, cluster, explain, and export the entity graph"
        kind="finding"
        density={density}
        actions={
          <div
            className="gw-toolbar"
            role="group"
            aria-label="Graph export actions"
          >
            <button
              type="button"
              data-testid="gw-export-json"
              onClick={() => void handleExport("json")}
            >
              JSON
            </button>
            <button
              type="button"
              data-testid="gw-export-dot"
              onClick={() => void handleExport("dot")}
            >
              DOT
            </button>
            <button
              type="button"
              data-testid="gw-export-mermaid"
              onClick={() => void handleExport("mermaid")}
            >
              Mermaid
            </button>
          </div>
        }
      >
        <div className="gw-stats">
          <V3Stat
            label="Nodes"
            value={graph.nodes.length}
            hint="entities in view"
          />
          <V3Stat
            label="Relationships"
            value={graph.edges.length}
            hint="typed links"
          />
          <V3Stat label="Clusters" value={chips.length} hint={dimension} />
          <V3Stat
            label="Cut vertices"
            value={structure?.cutVertices ?? "—"}
            hint="articulation points"
            tone={structure && structure.cutVertices > 0 ? "warn" : "neutral"}
          />
          <V3Stat
            label="Seed"
            value={options.seed}
            hint="deterministic layout"
          />
        </div>
        <LayoutSwitcher
          value={layoutKind}
          onChange={setLayoutKind}
          disabled={busy}
        />
        <ClusterChips
          chips={chips}
          selected={selectedCluster}
          dimension={dimension}
          onSelect={setSelectedCluster}
          onDimension={setDimension}
        />
        <div className="gw-body">
          <div className="gw-canvas-wrap">
            <div
              className="gw-canvas-toolbar"
              role="group"
              aria-label="Viewport controls"
            >
              <button
                type="button"
                aria-label="Zoom in"
                onClick={() =>
                  setViewport((v) =>
                    zoomAt(
                      v,
                      { x: options.width / 2, y: options.height / 2 },
                      1.2,
                    ),
                  )
                }
              >
                +
              </button>
              <button
                type="button"
                aria-label="Zoom out"
                onClick={() =>
                  setViewport((v) =>
                    zoomAt(
                      v,
                      { x: options.width / 2, y: options.height / 2 },
                      0.8,
                    ),
                  )
                }
              >
                −
              </button>
              <button
                type="button"
                data-testid="gw-fit"
                onClick={() =>
                  setViewport(
                    fitViewport(positions, {
                      width: options.width,
                      height: options.height,
                    }),
                  )
                }
              >
                Fit
              </button>
              <label className="gw-seed">
                <span>Seed</span>
                <input
                  type="number"
                  value={options.seed}
                  min={0}
                  max={999999}
                  aria-label="Layout seed"
                  data-testid="gw-seed"
                  onChange={(event) =>
                    setOptions(
                      layoutOptionsFrom({
                        seed: Number(event.target.value) || 0,
                      }),
                    )
                  }
                />
              </label>
            </div>
            <svg
              className="gw-canvas"
              data-testid="gw-canvas"
              viewBox={`0 0 ${options.width} ${options.height}`}
              role="img"
              aria-label="Analytical entity graph"
              data-strategy={layoutKind}
              onPointerDown={canvasPointerDown}
              onPointerMove={canvasPointerMove}
              onPointerUp={canvasPointerUp}
              onWheel={canvasWheel}
            >
              <g transform={transform}>
                {graph.edges.map((edge) => {
                  const left = positions[edge.source];
                  const right = positions[edge.target];
                  if (!left || !right) return null;
                  return (
                    <line
                      key={edgeKey(edge)}
                      x1={left.x}
                      y1={left.y}
                      x2={right.x}
                      y2={right.y}
                      className="gw-edge"
                      data-edge={edgeKey(edge)}
                      data-kind={edge.kind}
                      data-muted={
                        !visibleIds.has(edge.source) ||
                        !visibleIds.has(edge.target)
                      }
                    />
                  );
                })}
                {graph.nodes.map((node) => {
                  const point = positions[node.id];
                  if (!point) return null;
                  const color = KIND_COLORS[node.kind] ?? KIND_COLORS.note;
                  return (
                    <g
                      key={node.id}
                      className="gw-node"
                      data-node={node.id}
                      data-selected={node.id === selectedNode}
                      data-hovered={node.id === hoveredNode}
                      data-muted={!visibleIds.has(node.id)}
                      role="button"
                      tabIndex={0}
                      aria-label={`${node.label} (${node.kind})`}
                      onClick={() => handleNodeClick(node.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          handleNodeClick(node.id);
                        }
                      }}
                      onMouseEnter={() => setHoveredNode(node.id)}
                      onMouseLeave={() => setHoveredNode("")}
                    >
                      <circle
                        cx={point.x}
                        cy={point.y}
                        r={node.id === selectedNode ? 11 : 8}
                        fill={color}
                        stroke={
                          node.id === selectedNode ? "#f8fafc" : "transparent"
                        }
                        strokeWidth={2}
                      />
                      <text
                        x={point.x + 13}
                        y={point.y + 4}
                        className="gw-node__label"
                      >
                        {node.label}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
            <WorkbenchMinimap
              positions={positions}
              viewport={viewport}
              colors={KIND_COLORS}
              kinds={kinds}
              onNavigate={(world) =>
                setViewport((current) => ({
                  ...current,
                  x: world.x - current.width / (2 * current.zoom),
                  y: world.y - current.height / (2 * current.zoom),
                }))
              }
            />
          </div>
          <aside className="gw-side">
            <WorkbenchInspector model={inspector} allNodes={graph.nodes} />
            <RelationshipPanel
              gesture={gesture}
              historyText={historySummary(history)}
              canUndo={history.undo.length > 0}
              canRedo={history.redo.length > 0}
              busy={busy}
              lastRecord={lastRecord}
              onKind={(kind) => setGesture(setGestureKind(gesture, kind))}
              onLabel={(label) => setGesture(setGestureLabel(gesture, label))}
              onWeight={(weight) =>
                setGesture(setGestureWeight(gesture, weight))
              }
              onCommit={() => void handleCommit()}
              onCancel={() => setGesture(cancelGesture(gesture))}
              onUndo={() => void handleUndo()}
              onRedo={() => void handleRedo()}
              onSnapshot={() => void handleSnapshot()}
            />
          </aside>
        </div>
        <PathExplorer
          result={pathResult}
          source={pathSource}
          target={pathTarget}
          nodes={graph.nodes}
          onSource={setPathSource}
          onTarget={setPathTarget}
          onFind={() => void handleFindPath()}
          busy={busy}
        />
        {(notice || layoutResult.center) && (
          <footer className="gw-footer" data-testid="gw-footer" role="status">
            <span>{notice}</span>
            <span>
              layout={layoutResult.strategy} · hub={layoutResult.center || "—"}{" "}
              · updated {formatTimestamp(Date.now() / 1000)}
            </span>
          </footer>
        )}
      </V3Panel>
    </div>
  );
}

export default GraphWorkbench;
