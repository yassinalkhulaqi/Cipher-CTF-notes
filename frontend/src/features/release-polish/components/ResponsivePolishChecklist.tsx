/** Responsive polish checklist with breakpoint awareness. */

import { V3Panel, V3Stat } from "../../../v3/components/V3Panel";
import { BREAKPOINTS, POLISH_CHECKS } from "../config";
import {
  filterPolishByArea,
  formatPercent,
  polishAreas,
  polishProgress,
  resolveBreakpoint,
  responsiveRisk,
} from "../pure";
import type { PolishArea } from "../types";

export interface ResponsivePolishChecklistProps {
  checked: readonly string[];
  width: number;
  selectedArea: string;
  onToggle: (check: string) => void;
  onAreaChange: (area: string) => void;
}

export function ResponsivePolishChecklist({
  checked,
  width,
  selectedArea,
  onToggle,
  onAreaChange,
}: ResponsivePolishChecklistProps) {
  const active = POLISH_CHECKS.map((check) => ({
    ...check,
    done: checked.includes(check.id),
  }));
  const visible =
    selectedArea === "All"
      ? active
      : filterPolishByArea(active, selectedArea as PolishArea);
  const progress = polishProgress(active);
  const breakpoint = resolveBreakpoint(width, BREAKPOINTS);
  return (
    <V3Panel
      title="Responsive polish"
      subtitle={`${breakpoint} layout · ${responsiveRisk(breakpoint)} risk`}
      kind="target"
    >
      <div
        className="release-checklist"
        data-surface="responsive-polish-checklist"
        data-breakpoint={breakpoint}
        aria-label="Responsive polish checklist"
      >
        <div className="release-checklist__stats" data-role="checklist-stats">
          <V3Stat
            label="Complete"
            value={`${progress.done}/${progress.total}`}
          />
          <V3Stat
            label="Coverage"
            value={formatPercent(progress.percent)}
            tone="good"
          />
          <V3Stat label="Width" value={`${width}px`} hint={breakpoint} />
        </div>
        <div className="release-checklist__filters" data-role="area-filters">
          {["All", ...polishAreas(POLISH_CHECKS)].map((area) => (
            <button
              aria-label={`Filter polish by ${area}`}
              aria-pressed={selectedArea === area}
              className="release-v3-focusable"
              data-action="select-area"
              data-area={area}
              key={area}
              onClick={() => onAreaChange(area)}
              type="button"
            >
              {area}
            </button>
          ))}
        </div>
        <ul className="release-checklist__items" data-role="polish-items">
          {visible.map((check) => (
            <li
              className="release-checklist__item"
              data-check={check.id}
              data-state={check.done ? "done" : "open"}
              key={check.id}
            >
              <button
                aria-label={`Toggle ${check.label}`}
                aria-pressed={check.done}
                className="release-v3-focusable"
                data-action="toggle-check"
                onClick={() => onToggle(check.id)}
                type="button"
              >
                {check.done ? "Done" : "Open"}
              </button>
              <div>
                <strong>{check.label}</strong>
                <p>{check.detail}</p>
              </div>
              <span data-severity={check.severity}>{check.severity}</span>
            </li>
          ))}
        </ul>
      </div>
    </V3Panel>
  );
}
