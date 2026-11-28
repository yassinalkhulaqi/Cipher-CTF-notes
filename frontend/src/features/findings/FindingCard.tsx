import type { KeyboardEvent } from "react";

import { formatScore, severityTone, shortRef } from "./logic";
import type { FindingWire } from "./types";

export interface FindingCardProps {
  finding: FindingWire;
  selected?: boolean;
  onSelect?: (ref: string) => void;
  compact?: boolean;
}

const STATE_LABELS: Record<string, string> = {
  draft: "Draft",
  confirmed: "Confirmed",
  remediated: "Remediated",
  retested: "Retested",
  closed: "Closed",
};

export function FindingCard({
  finding,
  selected = false,
  onSelect,
  compact = false,
}: FindingCardProps) {
  const activate = () => onSelect?.(finding.ref);
  const handleKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate();
    }
  };
  return (
    <article
      className="finding-card"
      data-testid="finding-card"
      data-severity={finding.severity}
      data-state={finding.state}
      data-selected={selected}
      data-density={compact ? "compact" : "comfortable"}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      aria-label={`Select finding ${finding.title}`}
      onClick={activate}
      onKeyDown={handleKey}
    >
      <span className="finding-card__rail" aria-hidden="true" />
      <div className="finding-card__body">
        <div className="finding-card__heading">
          <span className="finding-card__ref">{shortRef(finding.ref)}</span>
          <span className="finding-card__state">
            {STATE_LABELS[finding.state] ?? finding.state}
          </span>
        </div>
        <h3 className="finding-card__title">{finding.title}</h3>
        {!compact && finding.summary && (
          <p className="finding-card__summary">{finding.summary}</p>
        )}
        <div className="finding-card__meta">
          <span
            className="finding-card__score"
            data-tone={severityTone(finding.severity)}
          >
            {formatScore(finding.score)}
          </span>
          <span className="finding-card__severity">{finding.severity}</span>
          {finding.duplicate_of && (
            <span className="finding-card__badge">duplicate</span>
          )}
          {finding.proof_blocks.length > 0 && (
            <span className="finding-card__badge">
              {finding.proof_blocks.length} proof
            </span>
          )}
          {finding.remediation.length > 0 && (
            <span className="finding-card__badge">
              {finding.remediation_progress * 100}% fixed
            </span>
          )}
        </div>
        {!compact && finding.tags.length > 0 && (
          <ul className="finding-card__tags">
            {finding.tags.map((tag) => (
              <li key={tag}>{tag}</li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
