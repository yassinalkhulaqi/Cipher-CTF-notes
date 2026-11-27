import { useMemo } from "react";
import type { ReactElement } from "react";

import type { GraphAction, GraphWorkbenchState, LayoutName } from "./state";
import {
  filterSummary,
  inspectNode,
  legendFor,
  nodeLabel,
  uniqueKinds,
  visibleEdges,
  visibleNodes,
} from "./state";

import "./graph-workbench.css";

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 600;
const LAYOUT_OPTIONS: { value: LayoutName; label: string }[] = [
  { value: "force", label: "Force" },
  { value: "circular", label: "Circle" },
  { value: "grid", label: "Grid" },
];
const RELATION_COLORS = [
  "var(--v4-accent)",
  "var(--v4-info)",
  "var(--v4-success)",
  "var(--v4-warning)",
  "var(--v4-danger)",
];

export interface GraphCanvasProps {
  state: GraphWorkbenchState;
  dispatch: (action: GraphAction) => void;
  title?: string;
  onNodeActivate?: (nodeId: string) => void;
}

export function relationColor(relation: string): string {
  let hash = 0;
  for (const char of relation) hash = (hash * 31 + char.charCodeAt(0)) % 997;
  return RELATION_COLORS[hash % RELATION_COLORS.length];
}

function initials(label: string): string {
  return label
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

export function GraphCanvas({
  state,
  dispatch,
  title = "Graph workbench",
  onNodeActivate,
}: GraphCanvasProps): ReactElement {
  const nodes = useMemo(() => visibleNodes(state), [state.nodes, state.filter]);
  const edges = useMemo(
    () => visibleEdges(state),
    [state.nodes, state.edges, state.filter],
  );
  const legend = useMemo(() => legendFor(edges), [edges]);
  const allRelations = useMemo(() => legendFor(state.edges), [state.edges]);
  const kinds = useMemo(() => uniqueKinds(state.nodes), [state.nodes]);
  const inspected = useMemo(
    () => inspectNode(state, state.selectedNodeId),
    [state.nodes, state.edges, state.selectedNodeId],
  );
  const highlighted = useMemo(() => {
    const ids = new Set<string>();
    const focus = state.hoveredNodeId ?? state.selectedNodeId;
    if (focus) {
      ids.add(focus);
      for (const edge of state.edges) {
        if (edge.source === focus) ids.add(edge.target);
        if (edge.target === focus) ids.add(edge.source);
      }
    }
    return ids;
  }, [state.edges, state.hoveredNodeId, state.selectedNodeId]);

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    nodes.forEach((node, index) => {
      const point = state.points[node.id];
      if (point) {
        map.set(node.id, { x: point.x, y: point.y });
        return;
      }
      const angle = (2 * Math.PI * index) / Math.max(1, nodes.length);
      map.set(node.id, {
        x: 480 + 300 * Math.cos(angle),
        y: 300 + 220 * Math.sin(angle),
      });
    });
    return map;
  }, [nodes, state.points]);

  const selectNode = (nodeId: string): void => {
    dispatch({ type: "select-node", nodeId });
    onNodeActivate?.(nodeId);
  };

  const metrics = state.metrics;

  return (
    <section className="v4-gw" aria-label={title}>
      <header className="v4-gw__header v4-panel">
        <div className="v4-gw__heading">
          <h2 className="v4-gw__title">{title}</h2>
          <span
            className={`v4-chip v4-gw__status v4-gw__status--${state.status}`}
          >
            {state.status}
          </span>
        </div>
        <div className="v4-gw__layouts" role="group" aria-label="Graph layout">
          {LAYOUT_OPTIONS.map((option) => (
            <button
              className={`v4-btn v4-gw__layout ${state.layout === option.value ? "v4-gw__layout--active" : ""}`}
              key={option.value}
              type="button"
              aria-pressed={state.layout === option.value}
              onClick={() =>
                dispatch({ type: "set-layout", layout: option.value })
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      <div className="v4-gw__metrics" aria-label="Graph metrics">
        <span className="v4-chip">
          Nodes {metrics?.node_count ?? nodes.length}
        </span>
        <span className="v4-chip">
          Edges {metrics?.edge_count ?? edges.length}
        </span>
        <span className="v4-chip">
          Components {metrics?.component_count ?? 0}
        </span>
        <span className="v4-chip">Isolated {metrics?.isolated_count ?? 0}</span>
        <span className="v4-chip">
          Density {metrics?.density.toFixed(3) ?? "0.000"}
        </span>
        <span className="v4-chip v4-chip--accent">
          Hidden {state.hiddenNodes}/{state.hiddenEdges}
        </span>
      </div>

      <div className="v4-gw__body">
        <aside className="v4-gw__rail v4-panel" aria-label="Graph filters">
          <h3 className="v4-gw__section-title">Filters</h3>
          <p className="v4-gw__hint">{filterSummary(state)}</p>

          <fieldset className="v4-gw__fieldset">
            <legend>Entity kinds</legend>
            {kinds.map((kind) => (
              <label className="v4-gw__check" key={kind}>
                <input
                  type="checkbox"
                  checked={state.filter.kinds.includes(kind)}
                  onChange={() => dispatch({ type: "toggle-kind", kind })}
                />
                <span>{kind}</span>
              </label>
            ))}
            {kinds.length === 0 && (
              <span className="v4-gw__muted">No nodes loaded</span>
            )}
          </fieldset>

          <fieldset className="v4-gw__fieldset">
            <legend>Relations</legend>
            {allRelations.map((item) => (
              <label className="v4-gw__check" key={item.relation}>
                <input
                  type="checkbox"
                  checked={state.filter.relations.includes(item.relation)}
                  onChange={() =>
                    dispatch({
                      type: "toggle-relation",
                      relation: item.relation,
                    })
                  }
                />
                <span>{item.relation}</span>
                <span className="v4-gw__count">{item.count}</span>
              </label>
            ))}
            {allRelations.length === 0 && (
              <span className="v4-gw__muted">No relations loaded</span>
            )}
          </fieldset>

          <label className="v4-gw__field">
            <span>Minimum weight ({state.filter.minWeight.toFixed(2)})</span>
            <input
              className="v4-gw__range v4-focus-ring"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={state.filter.minWeight}
              onChange={(event) =>
                dispatch({
                  type: "set-min-weight",
                  value: Number(event.target.value),
                })
              }
            />
          </label>

          <label className="v4-gw__field">
            <span>Label contains</span>
            <input
              className="v4-gw__input v4-focus-ring"
              type="search"
              value={state.filter.labelContains}
              placeholder="e.g. finding"
              onChange={(event) =>
                dispatch({ type: "set-label", value: event.target.value })
              }
            />
          </label>

          <button
            className="v4-btn v4-gw__reset"
            type="button"
            onClick={() => dispatch({ type: "reset-filter" })}
          >
            Reset filters
          </button>
        </aside>

        <div className="v4-gw__stage v4-panel">
          {state.error && <div className="v4-gw__error">{state.error}</div>}
          {nodes.length === 0 ? (
            <div className="v4-empty v4-gw__empty">
              <strong>No visible nodes</strong>
              <span>Adjust the filters or load a graph snapshot.</span>
            </div>
          ) : (
            <svg
              className="v4-gw__svg"
              viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
              role="img"
              aria-label={`${nodes.length} nodes and ${edges.length} relationships`}
            >
              <g className="v4-gw__edges">
                {edges.map((edge) => {
                  const from = positions.get(edge.source);
                  const to = positions.get(edge.target);
                  if (!from || !to) return null;
                  const dim =
                    highlighted.size > 0 &&
                    (!highlighted.has(edge.source) ||
                      !highlighted.has(edge.target));
                  return (
                    <line
                      key={`${edge.source}-${edge.target}-${edge.relation}`}
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke={relationColor(edge.relation)}
                      strokeWidth={0.8 + edge.weight * 2.4}
                      strokeOpacity={dim ? 0.12 : 0.55}
                      strokeLinecap="round"
                    />
                  );
                })}
              </g>
              <g className="v4-gw__nodes">
                {nodes.map((node) => {
                  const point = positions.get(node.id);
                  if (!point) return null;
                  const selected = state.selectedNodeId === node.id;
                  const dim = highlighted.size > 0 && !highlighted.has(node.id);
                  return (
                    <g
                      className={`v4-gw__node v4-gw__node--${node.kind} ${selected ? "v4-gw__node--selected" : ""}`}
                      key={node.id}
                      role="button"
                      tabIndex={0}
                      aria-label={node.label}
                      opacity={dim ? 0.35 : 1}
                      onClick={() => selectNode(node.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ")
                          selectNode(node.id);
                      }}
                      onMouseEnter={() =>
                        dispatch({ type: "hover-node", nodeId: node.id })
                      }
                      onMouseLeave={() =>
                        dispatch({ type: "hover-node", nodeId: null })
                      }
                    >
                      <circle
                        cx={point.x}
                        cy={point.y}
                        r={selected ? 22 : 17 + node.weight * 4}
                        fill="var(--v4-surface)"
                        stroke="var(--v4-accent)"
                        strokeWidth={selected ? 3 : 1.5}
                      />
                      <text x={point.x} y={point.y + 4} textAnchor="middle">
                        {initials(node.label)}
                      </text>
                      <title>{node.label}</title>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </div>

        <aside
          className="v4-gw__inspector v4-panel"
          aria-label="Node inspector"
        >
          <h3 className="v4-gw__section-title">Inspector</h3>
          {!inspected ? (
            <div className="v4-empty v4-gw__empty">
              <strong>No node selected</strong>
              <span>Select a node to inspect its relationships.</span>
            </div>
          ) : (
            <div className="v4-gw__inspect">
              <span className="v4-chip v4-chip--accent">
                {inspected.node.kind}
              </span>
              <h4 className="v4-gw__node-title">{inspected.node.label}</h4>
              <code className="v4-gw__node-id">{inspected.node.id}</code>
              <dl className="v4-gw__stats">
                <div>
                  <dt>Degree</dt>
                  <dd>{inspected.degree}</dd>
                </div>
                <div>
                  <dt>Outgoing</dt>
                  <dd>{inspected.outgoing}</dd>
                </div>
                <div>
                  <dt>Incoming</dt>
                  <dd>{inspected.incoming}</dd>
                </div>
              </dl>
              <h5>Relations</h5>
              <div className="v4-gw__tags">
                {inspected.relations.length === 0 && (
                  <span className="v4-gw__muted">None</span>
                )}
                {inspected.relations.map((relation) => (
                  <span className="v4-chip" key={relation}>
                    {relation}
                  </span>
                ))}
              </div>
              <h5>Neighbours</h5>
              <div className="v4-gw__neighbours">
                {inspected.neighbors.length === 0 && (
                  <span className="v4-gw__muted">Isolated</span>
                )}
                {inspected.neighbors.map((neighborId) => (
                  <button
                    className="v4-btn v4-gw__neighbour"
                    key={neighborId}
                    type="button"
                    onClick={() => selectNode(neighborId)}
                  >
                    {nodeLabel(state, neighborId)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>

      <footer
        className="v4-gw__legend v4-panel"
        aria-label="Relationship legend"
      >
        <h3 className="v4-gw__section-title">Relationship legend</h3>
        <ul className="v4-gw__legend-list">
          {legend.map((item) => (
            <li className="v4-gw__legend-item" key={item.relation}>
              <span
                className="v4-gw__swatch"
                style={{ background: relationColor(item.relation) }}
              />
              <span className="v4-gw__legend-name">{item.relation}</span>
              <span className="v4-gw__count">{item.count}</span>
              <span className="v4-gw__muted">
                avg {item.average_weight.toFixed(2)}
              </span>
            </li>
          ))}
          {legend.length === 0 && (
            <li className="v4-gw__muted">No visible relationships</li>
          )}
        </ul>
      </footer>
    </section>
  );
}

export default GraphCanvas;
