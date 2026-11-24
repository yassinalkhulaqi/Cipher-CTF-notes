/** One linkable activity row. */

import { entryMeta, entryTone, formatClock, redactionNote, truncate } from "../format";
import type { ActivityEntry, DensityMode, JumpTarget } from "../types";

export interface ActivityEntryRowProps {
  entry: ActivityEntry;
  density: DensityMode;
  now: number;
  selected: boolean;
  onSelect: (sequence: number) => void;
  onJump: (target: JumpTarget) => void;
}

export function ActivityEntryRow({
  entry,
  density,
  now,
  selected,
  onSelect,
  onJump,
}: ActivityEntryRowProps) {
  const jump = entry.jump;
  const detail = redactionNote(entry);
  return (
    <li
      className="activity-entry"
      data-density={density}
      data-tone={entryTone(entry)}
      data-selected={selected ? "true" : "false"}
    >
      <button
        type="button"
        className="activity-entry__main"
        onClick={() => onSelect(entry.sequence)}
        aria-label={`Select ${entry.title}`}
      >
        <time className="activity-entry__time" dateTime={entry.iso_timestamp}>
          {formatClock(entry.timestamp)}
        </time>
        <span className="activity-entry__severity">{entry.severity}</span>
        <span className="activity-entry__title">{entry.title}</span>
        {density !== "compact" && entry.summary && (
          <span className="activity-entry__summary">{truncate(entry.summary, 120)}</span>
        )}
        <span className="activity-entry__meta">{entryMeta(entry, density, now)}</span>
        {detail && <span className="activity-entry__redaction">{detail}</span>}
      </button>
      {jump?.resolvable && (
        <button
          type="button"
          className="activity-entry__jump"
          onClick={() => onJump(jump)}
          title={`Open ${jump.label}`}
        >
          Open {jump.kind}
        </button>
      )}
      {density === "detailed" && entry.payload && (
        <pre className="activity-entry__payload">
          {JSON.stringify(entry.payload, null, 2)}
        </pre>
      )}
    </li>
  );
}
