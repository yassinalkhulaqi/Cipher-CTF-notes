/** Chain-of-custody timeline and depth-lane visualization. */

import { useMemo, useState } from "react";

import {
  custodyColumns,
  custodyHeadline,
  custodyIssues,
  eventHashLabel,
} from "../custodyModel";
import { formatOffset, kindLabel, truncateMiddle } from "../format";
import type { CustodyGraphData } from "../types";

export interface CustodyTimelineProps {
  graph: CustodyGraphData | null;
  onSelect?: (ref: string) => void;
}

export function CustodyTimeline({ graph, onSelect }: CustodyTimelineProps) {
  const [selected, setSelected] = useState("");
  const columns = useMemo(() => custodyColumns(graph), [graph]);
  const issues = useMemo(() => custodyIssues(graph), [graph]);

  if (!graph) {
    return (
      <div className="elf-custody__empty" data-testid="custody-empty">
        No custody chain has been loaded for this evidence.
      </div>
    );
  }

  return (
    <div className="elf-custody" data-testid="custody-timeline">
      <header className="elf-custody__header">
        <div>
          <h3>Custody chain</h3>
          <p data-testid="custody-headline">{custodyHeadline(graph)}</p>
        </div>
        <span className="elf-pill" data-tone={graph.verified ? "good" : "bad"}>
          {graph.verified ? "Chain verified" : "Chain problems"}
        </span>
      </header>
      {issues.length > 0 && (
        <ul className="elf-custody__issues" data-testid="custody-issues">
          {issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
      <div className="elf-custody__lanes" data-testid="custody-lanes">
        {columns.map((column, depth) => (
          <div key={depth} className="elf-custody__lane" data-depth={depth}>
            <span className="elf-custody__lane-title">Depth {depth}</span>
            {column.map((node) => (
              <button
                key={node.ref}
                type="button"
                className="elf-custody__node"
                data-testid="custody-node"
                data-selected={selected === node.ref}
                data-kind={node.kind}
                aria-label={`Custody node ${node.label}`}
                onClick={() => {
                  setSelected(node.ref);
                  onSelect?.(node.ref);
                }}
              >
                <span className="elf-custody__node-action">
                  {node.action ? kindLabel(node.action) : kindLabel(node.kind)}
                </span>
                <span className="elf-custody__node-label" title={node.label}>
                  {truncateMiddle(node.label, 28)}
                </span>
                <span className="elf-custody__node-ref">
                  0x{formatOffset(depth)} · {node.ref}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="elf-custody__timeline" data-testid="custody-entries">
        {graph.timeline.map((group) => (
          <section key={group.date} className="elf-custody__day">
            <h4>{group.date}</h4>
            <ol>
              {group.events.map((event) => (
                <li
                  key={`${event.sequence}-${event.node}`}
                  data-testid="custody-event"
                >
                  <span className="elf-custody__seq">#{event.sequence}</span>
                  <span className="elf-custody__action">
                    {kindLabel(event.action)}
                  </span>
                  <span className="elf-custody__desc">
                    {event.description || event.actor}
                  </span>
                  <code title={event.hash}>{eventHashLabel(event)}</code>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}
