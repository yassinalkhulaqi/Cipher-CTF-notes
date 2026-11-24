/** Path explorer with per-step explanations and endpoint selection. */

import { pathSummary, stepTone } from "./analysis";
import type { GraphNode, PathResult } from "./types";
import { SEVERITY_COLORS } from "./types";

export interface PathExplorerProps {
  result: PathResult | null;
  source: string;
  target: string;
  nodes: GraphNode[];
  onSource: (id: string) => void;
  onTarget: (id: string) => void;
  onFind: () => void;
  busy?: boolean;
}

function labelFor(nodes: GraphNode[], id: string): string {
  return (
    nodes.find((node) => node.id === id)?.label || id || "Select an entity"
  );
}

export function PathExplorer({
  result,
  source,
  target,
  nodes,
  onSource,
  onTarget,
  onFind,
  busy = false,
}: PathExplorerProps) {
  return (
    <section className="gw-path" data-testid="gw-path-explorer">
      <header className="gw-section-header">
        <h3>Path explorer</h3>
        <span className="gw-section-hint">
          Explain how any two entities connect
        </span>
      </header>
      <div className="gw-path__controls">
        <label>
          <span>From</span>
          <select
            value={source}
            data-testid="gw-path-source"
            aria-label="Path source entity"
            onChange={(event) => onSource(event.target.value)}
          >
            <option value="">Select entity…</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {node.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>To</span>
          <select
            value={target}
            data-testid="gw-path-target"
            aria-label="Path target entity"
            onChange={(event) => onTarget(event.target.value)}
          >
            <option value="">Select entity…</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {node.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="gw-primary"
          data-testid="gw-path-find"
          disabled={!source || !target || busy}
          onClick={onFind}
        >
          Explain path
        </button>
      </div>
      {result && (
        <div
          className="gw-path__result"
          data-found={result.found}
          data-testid="gw-path-result"
        >
          <div className="gw-path__summary">
            <strong>{labelFor(nodes, source)}</strong>
            <span aria-hidden="true"> → </span>
            <strong>{labelFor(nodes, target)}</strong>
            <span className="gw-path__metric">{pathSummary(result)}</span>
          </div>
          {result.found && result.steps.length > 0 && (
            <ol className="gw-steps">
              {result.steps.map((step) => (
                <li
                  key={step.index}
                  data-tone={stepTone(step)}
                  data-testid="gw-path-step"
                >
                  <span
                    className="gw-steps__marker"
                    style={{
                      background:
                        SEVERITY_COLORS[step.kind] ?? SEVERITY_COLORS.info,
                    }}
                    aria-hidden="true"
                  />
                  <div>
                    <span className="gw-steps__kind">{step.kind}</span>
                    <p>{step.explanation}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
