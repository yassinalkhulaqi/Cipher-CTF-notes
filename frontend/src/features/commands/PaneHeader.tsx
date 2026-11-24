/** Header for one workspace pane with its own context and breadcrumbs. */

import { BreadcrumbTrail } from "./BreadcrumbTrail";
import type { NavNode, PaneSpec } from "./types";

export interface PaneHeaderProps {
  pane: PaneSpec;
  crumbs: NavNode[];
  active: boolean;
  onActivate: () => void;
  onClose: () => void;
  onSplit: () => void;
  onCommandBar: () => void;
}

export function PaneHeader({
  pane,
  crumbs,
  active,
  onActivate,
  onClose,
  onSplit,
  onCommandBar,
}: PaneHeaderProps) {
  return (
    <header
      className="v3c-pane__header"
      data-testid={`pane-header-${pane.id}`}
      data-active={active}
      data-kind={pane.kind}
    >
      <button
        type="button"
        className="v3c-pane__title"
        aria-label={`Activate ${pane.title}`}
        onClick={onActivate}
      >
        {pane.title}
      </button>
      <span
        className="v3c-pane__context"
        data-testid={`pane-context-${pane.id}`}
      >
        {pane.context_ref || "No context"}
      </span>
      <BreadcrumbTrail crumbs={crumbs} compact />
      <div className="v3c-pane__actions">
        <button
          type="button"
          aria-label="Open command bar in this pane"
          onClick={onCommandBar}
        >
          ⌘K
        </button>
        <button type="button" aria-label="Split pane" onClick={onSplit}>
          Split
        </button>
        <button
          type="button"
          aria-label={`Close ${pane.title}`}
          onClick={onClose}
          disabled={!pane.closable}
        >
          Close
        </button>
      </div>
    </header>
  );
}
