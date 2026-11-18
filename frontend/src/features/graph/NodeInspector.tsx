import {
  breadcrumbs,
  buildInspectorModel,
  formatCount,
  formatScore,
  inspectorTitle,
  recommendationLabel,
  truncateLabel,
} from "./inspector";
import type { InspectorState } from "./inspector";
import type {
  GraphLinkDetail,
  GraphPayload,
  GraphRecommendation,
} from "./types";

interface NodeInspectorProps {
  payload: GraphPayload;
  selectedId: number | null;
  state: InspectorState;
  links: GraphLinkDetail | null;
  recommendations: GraphRecommendation[];
  onSelect: (id: number) => void;
  onToggle: (key: string) => void;
  onOpenNote?: (id: number) => void;
}

export function NodeInspector({
  payload,
  selectedId,
  state,
  links,
  recommendations,
  onSelect,
  onToggle,
  onOpenNote,
}: NodeInspectorProps) {
  const model =
    selectedId === null
      ? null
      : buildInspectorModel(payload, selectedId, links, recommendations);

  if (!model) {
    return (
      <aside
        className="graph-inspector graph-inspector-empty"
        aria-label="Node inspector"
      >
        <h3>Node inspector</h3>
        <p>Select a node to see its links and metadata.</p>
      </aside>
    );
  }

  const crumbs = breadcrumbs(model.node);
  const backlinks = model.links?.backlinks ?? [];
  const unresolved = model.links?.unresolved ?? [];

  return (
    <aside className="graph-inspector" aria-label="Node inspector">
      <header className="graph-inspector-header">
        <span className="graph-inspector-kind">{model.node.kind}</span>
        <h3 title={model.node.label}>{inspectorTitle(model)}</h3>
        <p className="graph-inspector-crumbs">
          {crumbs.map((crumb) => truncateLabel(crumb, 18)).join(" / ")}
        </p>
      </header>

      <dl className="graph-inspector-stats">
        <div>
          <dt>Degree</dt>
          <dd>{formatScore(model.degree)}</dd>
        </div>
        <div>
          <dt>Backlinks</dt>
          <dd>{backlinks.length}</dd>
        </div>
        <div>
          <dt>Outlinks</dt>
          <dd>{model.links?.outlinks.length ?? 0}</dd>
        </div>
        <div>
          <dt>Unresolved</dt>
          <dd>{unresolved.length}</dd>
        </div>
      </dl>

      {model.tags.length > 0 && (
        <section className="graph-inspector-section">
          <h4>Tags</h4>
          <div className="graph-chip-row">
            {model.tags.map((tag) => (
              <span className="graph-chip" key={tag}>
                #{tag}
              </span>
            ))}
          </div>
        </section>
      )}

      {model.neighbors.map((group) => (
        <section className="graph-inspector-section" key={group.kind}>
          <button
            type="button"
            className="graph-section-toggle"
            onClick={() => onToggle(group.kind)}
            aria-expanded={state.expanded[group.kind] === true}
          >
            {group.kind} · {formatCount(group.nodes.length, "neighbor")}
          </button>
          {state.expanded[group.kind] && (
            <ul className="graph-neighbor-list">
              {group.nodes.map((node) => (
                <li key={node.id}>
                  <button type="button" onClick={() => onSelect(node.id)}>
                    {truncateLabel(node.label, 34)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}

      {model.recommendations.length > 0 && (
        <section className="graph-inspector-section">
          <h4>Recommendations</h4>
          <ul className="graph-neighbor-list">
            {model.recommendations.slice(0, 5).map((item) => (
              <li key={`${item.source_id}-${item.target_id}`}>
                <button type="button" onClick={() => onSelect(item.target_id)}>
                  {recommendationLabel(item)} · {formatScore(item.score)}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {onOpenNote && (
        <button
          type="button"
          className="graph-open-note"
          onClick={() => onOpenNote(model.node.id)}
        >
          Open note
        </button>
      )}
    </aside>
  );
}
