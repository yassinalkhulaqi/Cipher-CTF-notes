import { useEffect, useMemo, useState } from "react";
import { fitViewport, identityViewport } from "./canvas";
import { buildClusters, visibleNodeIds } from "./clusters";
import type { ClusterStrategy } from "./clusters";
import {
  activeFilterCount,
  filterGraph,
  filterSummary,
  toggleValue,
  withFilterDefaults,
} from "./filters";
import { layoutGraph, normalizePositions } from "./layout";
import { GraphCanvas } from "./GraphCanvas";
import { NodeInspector } from "./NodeInspector";
import { PathExplorer } from "./PathExplorer";
import {
  defaultInspectorState,
  selectInspectorNode,
  toggleInspectorSection,
} from "./inspector";
import { findGraphPath, pathNodeIds, pushPathHistory } from "./pathAlgorithms";
import type {
  GraphEdge,
  GraphFilterState,
  GraphLinkDetail,
  GraphNode,
  GraphPayload,
  GraphPathPayload,
  GraphRecommendation,
  LayoutKind,
  Size,
  Viewport,
} from "./types";
import { DEFAULT_FILTERS, DEFAULT_LAYOUT, GRAPH_NODE_KINDS } from "./types";

interface GraphFeatureProps {
  payload: GraphPayload;
  initialFilters?: Partial<GraphFilterState>;
  links?: Record<number, GraphLinkDetail>;
  recommendations?: GraphRecommendation[];
  onOpenNote?: (id: number) => void;
  onEdgeSelect?: (edge: GraphEdge | null) => void;
}

const LAYOUTS: LayoutKind[] = ["force", "circle", "grid", "radial", "tree"];
const STRATEGIES: ClusterStrategy[] = ["component", "tag", "kind"];
const STAGE_SIZE: Size = { width: 900, height: 620 };

export function GraphFeature({
  payload,
  initialFilters,
  links = {},
  recommendations = [],
  onOpenNote,
  onEdgeSelect,
}: GraphFeatureProps) {
  const [filters, setFilters] = useState<GraphFilterState>(
    withFilterDefaults({ ...DEFAULT_FILTERS, ...initialFilters }),
  );
  const [layoutKind, setLayoutKind] = useState<LayoutKind>("force");
  const [strategy, setStrategy] = useState<ClusterStrategy>("component");
  const [collapsedIds, setCollapsedIds] = useState<number[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [inspector, setInspector] = useState(defaultInspectorState());
  const [viewport, setViewport] = useState<Viewport>(identityViewport());
  const [sourceId, setSourceId] = useState<number | null>(null);
  const [targetId, setTargetId] = useState<number | null>(null);
  const [path, setPath] = useState<GraphPathPayload | null>(null);
  const [history, setHistory] = useState<GraphPathPayload[]>([]);

  const filtered = useMemo(
    () => filterGraph(payload, filters),
    [payload, filters],
  );
  const baseClusters = useMemo(
    () => buildClusters(filtered, strategy),
    [filtered, strategy],
  );
  const clusters = useMemo(
    () =>
      baseClusters.map((cluster) => ({
        ...cluster,
        collapsed: collapsedIds.includes(cluster.id),
      })),
    [baseClusters, collapsedIds],
  );
  const positions = useMemo(() => {
    const computed = layoutGraph(filtered.nodes, filtered.edges, layoutKind, {
      ...DEFAULT_LAYOUT,
      kind: layoutKind,
      ...STAGE_SIZE,
    });
    return normalizePositions(computed, STAGE_SIZE.width, STAGE_SIZE.height);
  }, [filtered, layoutKind]);

  useEffect(() => {
    setCollapsedIds([]);
  }, [baseClusters]);

  useEffect(() => {
    setViewport(fitViewport(positions, STAGE_SIZE));
  }, [positions]);

  const visible = useMemo(() => visibleNodeIds(clusters), [clusters]);
  const visibleNodes = useMemo(
    () => filtered.nodes.filter((node) => visible.has(node.id)),
    [filtered.nodes, visible],
  );
  const visibleEdges = useMemo(
    () =>
      filtered.edges.filter(
        (edge) => visible.has(edge.source) && visible.has(edge.target),
      ),
    [filtered.edges, visible],
  );
  const highlighted = useMemo(() => pathNodeIds(path), [path]);
  const allCollapsed =
    clusters.length > 0 && clusters.every((cluster) => cluster.collapsed);

  const selectNode = (id: number | null) => {
    setSelectedId(id);
    setInspector((state) => selectInspectorNode(state, id));
  };

  const findPath = () => {
    if (sourceId === null || targetId === null) return;
    const result = findGraphPath(filtered, sourceId, targetId);
    setPath(result);
    setHistory((items) => pushPathHistory(items, result));
  };

  const toggleKind = (kind: GraphNode["kind"]) => {
    setFilters((state) => ({
      ...state,
      kinds: toggleValue(state.kinds, kind),
    }));
  };

  const toggleCluster = (id: number) => {
    setCollapsedIds((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  };

  return (
    <section className="graph-feature" aria-label="Graph intelligence">
      <header className="graph-feature-header">
        <div>
          <h2>Graph intelligence</h2>
          <p>{filterSummary(filters)}</p>
        </div>
        <div className="graph-feature-tools">
          <label>
            <span>Search</span>
            <input
              type="search"
              value={filters.query}
              placeholder="Filter by title, path, or tag"
              onChange={(event) =>
                setFilters((state) => ({ ...state, query: event.target.value }))
              }
            />
          </label>
          <label>
            <span>Layout</span>
            <select
              value={layoutKind}
              onChange={(event) =>
                setLayoutKind(event.target.value as LayoutKind)
              }
            >
              {LAYOUTS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Clusters</span>
            <select
              value={strategy}
              onChange={(event) =>
                setStrategy(event.target.value as ClusterStrategy)
              }
            >
              {STRATEGIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => setViewport(fitViewport(positions, STAGE_SIZE))}
          >
            Fit
          </button>
        </div>
      </header>

      <div className="graph-kind-pills">
        {GRAPH_NODE_KINDS.map((kind) => (
          <button
            type="button"
            key={kind}
            className={filters.kinds.includes(kind) ? "active" : ""}
            onClick={() => toggleKind(kind)}
          >
            {kind}
          </button>
        ))}
        <span>{activeFilterCount(filters)} filters</span>
      </div>

      <div className="graph-cluster-controls">
        {clusters.map((cluster) => (
          <button
            type="button"
            key={cluster.id}
            onClick={() => toggleCluster(cluster.id)}
            className={cluster.collapsed ? "collapsed" : ""}
          >
            <i style={{ background: cluster.color }} />
            {cluster.label} · {cluster.size}
          </button>
        ))}
        <button
          type="button"
          onClick={() =>
            setCollapsedIds(
              allCollapsed ? [] : clusters.map((cluster) => cluster.id),
            )
          }
        >
          {allCollapsed ? "Expand all" : "Collapse all"}
        </button>
      </div>

      <div className="graph-feature-body">
        <div className="graph-stage">
          <GraphCanvas
            nodes={visibleNodes}
            edges={visibleEdges}
            positions={positions}
            clusters={clusters}
            viewport={viewport}
            selectedId={selectedId}
            highlighted={highlighted}
            onViewportChange={setViewport}
            onSelect={selectNode}
            onEdgeSelect={onEdgeSelect}
          />
        </div>
        <NodeInspector
          payload={filtered}
          selectedId={selectedId}
          state={inspector}
          links={selectedId === null ? null : (links[selectedId] ?? null)}
          recommendations={recommendations}
          onSelect={selectNode}
          onToggle={(key) =>
            setInspector((state) => toggleInspectorSection(state, key))
          }
          onOpenNote={onOpenNote}
        />
      </div>

      <PathExplorer
        payload={filtered}
        path={path}
        history={history}
        sourceId={sourceId}
        targetId={targetId}
        onSource={setSourceId}
        onTarget={setTargetId}
        onFind={findPath}
        onHistory={(item) => {
          setPath(item);
          setSourceId(item.node_ids?.[0] ?? null);
          setTargetId(item.node_ids?.[item.node_ids.length - 1] ?? null);
        }}
        onClear={() => {
          setPath(null);
          setSourceId(null);
          setTargetId(null);
        }}
      />
    </section>
  );
}
