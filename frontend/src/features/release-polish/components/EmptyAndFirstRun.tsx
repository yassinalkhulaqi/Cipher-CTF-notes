/** Empty and first-run states for the main release surfaces. */

import { V3Panel } from "../../../v3/components/V3Panel";
import { EMPTY_STATES } from "../config";
import { emptyStateFor } from "../pure";
import type { EmptyStateSpec, ReleaseCounts } from "../types";

export interface EmptyAndFirstRunProps {
  counts: ReleaseCounts;
  surface: string;
  dismissed: readonly string[];
  onAction: (route: string) => void;
  onDismiss: (surface: string) => void;
}

export function EmptyAndFirstRun({
  counts,
  surface,
  dismissed,
  onAction,
  onDismiss,
}: EmptyAndFirstRunProps) {
  const spec: EmptyStateSpec | undefined = emptyStateFor(surface, EMPTY_STATES);
  const isEmpty =
    (surface === "notes" && counts.notes === 0) ||
    (surface === "findings" && counts.findings === 0) ||
    (surface === "evidence" && counts.evidence === 0) ||
    (surface === "report" && counts.reports === 0);
  if (!spec || !isEmpty || dismissed.includes(spec.surface)) {
    return (
      <V3Panel title="Ready" subtitle="This surface has content." kind="report" density="compact">
        <p data-surface="empty-first-run" data-state="content" aria-label="Surface has content">
          Nothing to set up here.
        </p>
      </V3Panel>
    );
  }

  return (
    <V3Panel title={spec.title} subtitle={`Surface: ${spec.surface}`} kind="folder">
      <div
        className="release-empty"
        data-surface="empty-first-run"
        data-surface-name={spec.surface}
        aria-label={`${spec.title} empty state`}
      >
        <span className="release-empty__icon" data-icon={spec.icon} aria-hidden="true">
          {spec.icon}
        </span>
        <p className="release-empty__body">{spec.body}</p>
        <div className="release-empty__actions" data-role="empty-actions">
          <button
            aria-label={spec.actionLabel}
            className="release-v3-focusable"
            data-action="empty-primary"
            data-route={spec.actionRoute}
            onClick={() => onAction(spec.actionRoute)}
            type="button"
          >
            {spec.actionLabel}
          </button>
          <button
            aria-label={`Dismiss ${spec.title} hint`}
            className="release-v3-focusable"
            data-action="dismiss-empty"
            onClick={() => onDismiss(spec.surface)}
            type="button"
          >
            Not now
          </button>
        </div>
      </div>
    </V3Panel>
  );
}
