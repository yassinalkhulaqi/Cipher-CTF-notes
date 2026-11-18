import {
  formatHop,
  nodeById,
  pathEndpointLabels,
  pathKinds,
  pathLabel,
  pathSummary,
} from "./pathAlgorithms";
import type { GraphNode, GraphPathPayload, GraphPayload } from "./types";

interface PathExplorerProps {
  payload: GraphPayload;
  path: GraphPathPayload | null;
  history: GraphPathPayload[];
  sourceId: number | null;
  targetId: number | null;
  onSource: (id: number | null) => void;
  onTarget: (id: number | null) => void;
  onFind: () => void;
  onHistory: (path: GraphPathPayload) => void;
  onClear: () => void;
}

export function PathExplorer({
  payload,
  path,
  history,
  sourceId,
  targetId,
  onSource,
  onTarget,
  onFind,
  onHistory,
  onClear,
}: PathExplorerProps) {
  const endpoints = pathEndpointLabels(path);
  const summary = pathSummary(path);
  const options = payload.nodes;
  const renderOption = (node: GraphNode) => `${node.label} (#${node.id})`;

  return (
    <section className="graph-path-explorer" aria-label="Path explorer">
      <header>
        <h3>Path explorer</h3>
        <button type="button" onClick={onClear}>
          Clear
        </button>
      </header>

      <div className="graph-path-controls">
        <label>
          <span>From</span>
          <select
            value={sourceId ?? ""}
            onChange={(event) =>
              onSource(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">Select note</option>
            {options.map((node) => (
              <option key={`from-${node.id}`} value={node.id}>
                {renderOption(node)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>To</span>
          <select
            value={targetId ?? ""}
            onChange={(event) =>
              onTarget(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">Select note</option>
            {options.map((node) => (
              <option key={`to-${node.id}`} value={node.id}>
                {renderOption(node)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onFind}
          disabled={sourceId === null || targetId === null}
        >
          Find path
        </button>
      </div>

      {path && (
        <div className="graph-path-result">
          <p className="graph-path-route">{pathLabel(path)}</p>
          <p className="graph-path-meta">
            {String(summary.hops)} hops · cost {String(summary.cost)} ·{" "}
            {pathKinds(path).join(", ")}
          </p>
          <ol>
            {(path.node_ids ?? []).map((id, index, all) => (
              <li key={`${id}-${index}`}>
                <span>{nodeById(payload, id)?.label ?? String(id)}</span>
                <small>{formatHop(index, all.length)}</small>
              </li>
            ))}
          </ol>
          <p className="graph-path-endpoints">
            {endpoints.source} → {endpoints.target}
          </p>
        </div>
      )}

      {!path && (
        <p className="graph-path-empty">No path between the selected notes.</p>
      )}

      {history.length > 0 && (
        <div className="graph-path-history">
          <h4>Recent paths</h4>
          <ul>
            {history.map((item) => (
              <li key={(item.node_ids ?? []).join(":")}>
                <button type="button" onClick={() => onHistory(item)}>
                  {pathLabel(item, " · ")}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
