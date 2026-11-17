import type { LucideIcon } from "lucide-react";
import type { NodeSummary } from "../../lib/types";
import { relativeTime } from "../../lib/utils";
import { StatusIcon } from "../StatusIcon";

interface MiniNotesPanelProps {
  title: string;
  subtitle: string;
  notes: NodeSummary[];
  emptyText: string;
  actionIcon: LucideIcon;
  actionLabel: string;
  onAction: () => void;
  onOpen: (id: number) => void;
}

/** Compact notes list panel (active notes, pinned notes). */
export function MiniNotesPanel({
  title,
  subtitle,
  notes,
  emptyText,
  actionIcon: ActionIcon,
  actionLabel,
  onAction,
  onOpen,
}: MiniNotesPanelProps) {
  return (
    <section className="dash-panel compact" data-tilt data-reveal>
      <div className="dash-panel-head">
        <div>
          <h2>{title}</h2>
          <span>{subtitle}</span>
        </div>
        <button
          type="button"
          className="icon-btn sm"
          onClick={onAction}
          aria-label={actionLabel}
          title={actionLabel}
        >
          <ActionIcon />
        </button>
      </div>
      <div className="mini-list">
        {notes.length ? (
          notes.map((note) => (
            <button
              key={note.id}
              type="button"
              className="mini-row"
              onClick={() => onOpen(note.id)}
            >
              <StatusIcon status={note.status} />
              <span>{note.title}</span>
              <span className="mini-time">{relativeTime(note.updated_at)}</span>
            </button>
          ))
        ) : (
          <p className="mini-empty">{emptyText}</p>
        )}
      </div>
    </section>
  );
}
