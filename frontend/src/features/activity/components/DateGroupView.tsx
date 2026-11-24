/** Date-grouped section of the activity stream. */

import type { DateGroup, DensityMode, JumpTarget } from "../types";
import { formatDayLabel } from "../format";
import { ActivityEntryRow } from "./ActivityEntryRow";

export interface DateGroupViewProps {
  group: DateGroup;
  density: DensityMode;
  now: number;
  selectedSequence: number;
  onSelect: (sequence: number) => void;
  onJump: (target: JumpTarget) => void;
}

export function DateGroupView({
  group,
  density,
  now,
  selectedSequence,
  onSelect,
  onJump,
}: DateGroupViewProps) {
  return (
    <section className="activity-date-group" data-period={group.period}>
      <header className="activity-date-group__header">
        <h3>{formatDayLabel(group.key, now)}</h3>
        <span className="activity-date-group__count">{group.count}</span>
      </header>
      <ul className="activity-date-group__entries">
        {group.entries.map((entry) => (
          <ActivityEntryRow
            key={entry.sequence}
            entry={entry}
            density={density}
            now={now}
            selected={selectedSequence === entry.sequence}
            onSelect={onSelect}
            onJump={onJump}
          />
        ))}
      </ul>
    </section>
  );
}
