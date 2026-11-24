/** Pivot chips that navigate into the owning finding/evidence/report. */

import { groupPivotsByRole, pivotChipLabel, roleTone } from "../pivots";
import type { PivotContextV2, PivotSuggestionV2 } from "../types";

export interface PivotChipsProps {
  context?: PivotContextV2;
  onPivot?: (pivot: PivotSuggestionV2) => void;
}

export function PivotChips({ context, onPivot }: PivotChipsProps) {
  if (!context || !context.pivots.length) return null;
  const groups = groupPivotsByRole(context.pivots);
  return (
    <section
      aria-label={`Pivot from ${context.origin}`}
      className="si-pivots"
      data-origin={context.origin}
      data-testid="search-pivot-chips"
    >
      <header>
        <h3>Pivot from {context.origin_title || context.origin}</h3>
      </header>
      {groups.map((group) => (
        <div
          className="si-pivots__group"
          data-role={group.role}
          key={group.role}
        >
          <span className="si-pivots__role">{group.role}</span>
          <div className="si-pivots__chips">
            {group.items.map((pivot) => (
              <button
                aria-label={`Pivot to ${pivotChipLabel(pivot)}`}
                className="si-pivot-chip v3-focusable"
                data-kind={pivot.kind}
                data-ref={pivot.ref}
                data-testid="search-pivot-chip"
                data-tone={roleTone(pivot.role)}
                key={`${pivot.ref}-${pivot.role}`}
                onClick={() => onPivot?.(pivot)}
                title={pivot.reason}
                type="button"
              >
                {pivot.label || pivot.ref}
                <span className="si-pivot-chip__kind">{pivot.kind}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
