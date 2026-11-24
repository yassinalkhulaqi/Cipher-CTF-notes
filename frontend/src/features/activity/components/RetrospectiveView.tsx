/** Retrospective summary view. */

import { rankedLabel, retrospectiveTiles } from "../format";
import type { JumpTarget, RetrospectiveSummary } from "../types";

export interface RetrospectiveViewProps {
  summary: RetrospectiveSummary;
  onJump: (target: JumpTarget) => void;
}

export function RetrospectiveView({ summary, onJump }: RetrospectiveViewProps) {
  return (
    <section className="activity-retrospective">
      <header className="activity-retrospective__header">
        <h3>Retrospective</h3>
        <p>
          {summary.iso_start.slice(0, 10)} → {summary.iso_end.slice(0, 10)}
        </p>
      </header>
      <div className="activity-retrospective__tiles">
        {retrospectiveTiles(summary).map((tile) => (
          <div key={tile.label} className="activity-retrospective__tile">
            <span>{tile.label}</span>
            <strong>{tile.value}</strong>
          </div>
        ))}
      </div>
      <div className="activity-retrospective__rankings">
        <div>
          <h4>Top kinds</h4>
          <ul>
            {summary.top_kinds.map((item) => (
              <li key={item.value}>{rankedLabel(item)}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Top actors</h4>
          <ul>
            {summary.top_actors.map((item) => (
              <li key={item.value}>{rankedLabel(item)}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Highlights</h4>
          <ul>
            {summary.highlights.map((entry) => (
              <li key={entry.sequence}>
                <button
                  type="button"
                  className="activity-retrospective__jump"
                  disabled={!entry.jump?.resolvable}
                  onClick={() => entry.jump && onJump(entry.jump)}
                >
                  {entry.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
