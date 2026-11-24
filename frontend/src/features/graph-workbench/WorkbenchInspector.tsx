/** Entity metadata inspector built from the universal resolver payload. */

import {
  groupNeighbors,
  inspectorSections,
  inspectorTitle,
  severityColor,
} from "./inspector";
import type { InspectorModel } from "./types";

export interface WorkbenchInspectorProps {
  model: InspectorModel | null;
  allNodes?: Array<{ id: string; kind: string }>;
}

export function WorkbenchInspector({
  model,
  allNodes = [],
}: WorkbenchInspectorProps) {
  if (!model) {
    return (
      <section className="gw-inspector" data-testid="gw-inspector">
        <p className="gw-empty">
          Select a node to inspect its entity metadata.
        </p>
      </section>
    );
  }
  const sections = inspectorSections(model);
  const grouped = groupNeighbors(model.neighbors, allNodes);
  return (
    <section
      className="gw-inspector"
      data-testid="gw-inspector"
      data-node={model.id}
    >
      <header className="gw-inspector__header">
        <span
          className="gw-inspector__accent"
          style={{ background: severityColor(model.severity) }}
          aria-hidden="true"
        />
        <div>
          <h3 title={model.title}>{inspectorTitle(model)}</h3>
          <p className="gw-inspector__id">{model.id}</p>
        </div>
      </header>
      {sections.includes("identity") && (
        <div className="gw-inspector__section" data-section="identity">
          <h4>Identity</h4>
          <dl>
            <div>
              <dt>Kind</dt>
              <dd>{model.kind}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{model.status}</dd>
            </div>
            <div>
              <dt>Severity</dt>
              <dd data-severity={model.severity}>{model.severity}</dd>
            </div>
            <div>
              <dt>Owner</dt>
              <dd>{model.owner || "—"}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>v{model.version}</dd>
            </div>
          </dl>
          {model.summary && (
            <p className="gw-inspector__summary">{model.summary}</p>
          )}
        </div>
      )}
      {sections.includes("tags") && (
        <div className="gw-inspector__section" data-section="tags">
          <h4>Tags</h4>
          <ul className="gw-inspector__tags">
            {model.tags.map((tag) => (
              <li key={tag} data-tag={tag}>
                #{tag}
              </li>
            ))}
          </ul>
        </div>
      )}
      {sections.includes("clusters") && (
        <div className="gw-inspector__section" data-section="clusters">
          <h4>Clusters</h4>
          <ul className="gw-inspector__clusters">
            {Object.entries(model.clusters).map(([dimension, key]) => (
              <li key={dimension} data-dimension={dimension}>
                <span>{dimension}</span>
                <strong>{key || "unassigned"}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
      {sections.includes("relationships") && (
        <div className="gw-inspector__section" data-section="relationships">
          <h4>Relationships ({model.degree})</h4>
          {Object.entries(grouped).map(([kind, neighbors]) => (
            <div key={kind} className="gw-inspector__neighbors">
              <span className="gw-inspector__kind">{kind}</span>
              <ul>
                {neighbors.map((neighbor) => (
                  <li key={neighbor.id} data-neighbor={neighbor.id}>
                    {neighbor.label}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {model.degree === 0 && (
            <p className="gw-empty">No linked entities.</p>
          )}
        </div>
      )}
      {sections.includes("metadata") && (
        <div className="gw-inspector__section" data-section="metadata">
          <h4>Metadata</h4>
          <ul className="gw-inspector__metadata">
            {model.metadata.map((item) => (
              <li key={item.key} data-key={item.key}>
                <span>{item.key}</span>
                <code>{item.value}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
