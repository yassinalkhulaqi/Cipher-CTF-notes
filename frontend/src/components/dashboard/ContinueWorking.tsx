import { ArrowUpRight, ChevronRight, Flag } from "lucide-react";
import { STATUS_LABEL } from "../../lib/constants";
import type { NodeSummary } from "../../lib/types";
import { relativeTime } from "../../lib/utils";
import { StatusIcon } from "../StatusIcon";

interface ContinueWorkingProps {
  notes: NodeSummary[];
  onOpen: (id: number) => void;
  onJump: () => void;
}

/** "Recently updated notes" panel on the dashboard. */
export function ContinueWorking({
  notes,
  onOpen,
  onJump,
}: ContinueWorkingProps) {
  return (
    <section className="dash-panel" data-tilt data-reveal>
      <div className="dash-panel-head">
        <div>
          <h2>Continue working</h2>
          <span>Recently updated notes</span>
        </div>
        <button type="button" className="link-btn" onClick={onJump}>
          Jump to <ArrowUpRight />
        </button>
      </div>
      <div className="work-list">
        {notes.map((note, index) => (
          <button
            key={note.id}
            type="button"
            className="work-row"
            onClick={() => onOpen(note.id)}
          >
            <span className="work-index">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="work-state">
              <StatusIcon
                status={note.status}
                label={STATUS_LABEL[note.status]}
              />
            </span>
            <span className="work-copy">
              <span className="work-title">{note.title}</span>
              <span className="work-meta">
                {note.path || "Vault root"}
                {note.target ? ` · ${note.target}` : ""}
              </span>
            </span>
            {note.flag ? (
              <span className="work-flag">
                <Flag />
              </span>
            ) : null}
            {note.pinned ? <span className="work-pin">Pinned</span> : null}
            <span className="work-time">{relativeTime(note.updated_at)}</span>
            <ChevronRight className="work-arrow" />
          </button>
        ))}
      </div>
    </section>
  );
}
