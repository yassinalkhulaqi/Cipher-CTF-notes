/** Distraction-free focus session overlay. */

import type { FocusSession } from "./types";

export interface FocusOverlayProps {
  visible: boolean;
  session: FocusSession | null;
  onPause: () => void;
  onResume: () => void;
  onEnd: () => void;
  onInterrupt: () => void;
}

export function FocusOverlay({
  visible,
  session,
  onPause,
  onResume,
  onEnd,
  onInterrupt,
}: FocusOverlayProps) {
  if (!visible || !session || session.status === "ended") return null;
  return (
    <div
      className="v3c-focus"
      data-testid="focus-overlay"
      data-status={session.status}
      role="dialog"
      aria-label="Focus session"
    >
      <div className="v3c-focus__card">
        <span className="v3c-focus__eyebrow">Focus session</span>
        <h2 className="v3c-focus__title">{session.label}</h2>
        <p className="v3c-focus__target" data-testid="focus-target">
          {session.target || "This workspace"}
        </p>
        <dl className="v3c-focus__stats">
          <div>
            <dt>Status</dt>
            <dd>{session.status}</dd>
          </div>
          <div>
            <dt>Interruptions</dt>
            <dd data-testid="focus-interruptions">{session.interruptions}</dd>
          </div>
          <div>
            <dt>Restore to</dt>
            <dd>{session.restore_pane || "—"}</dd>
          </div>
        </dl>
        <div className="v3c-focus__actions">
          {session.status === "active" ? (
            <button type="button" className="v3c-button" onClick={onPause}>
              Pause
            </button>
          ) : (
            <button type="button" className="v3c-button" onClick={onResume}>
              Resume
            </button>
          )}
          <button type="button" className="v3c-button" onClick={onInterrupt}>
            Note interruption
          </button>
          <button
            type="button"
            className="v3c-button v3c-button--primary"
            onClick={onEnd}
          >
            End session
          </button>
        </div>
        <p className="v3c-focus__hint" role="status">
          Press Ctrl+K at any time to run a command.
        </p>
      </div>
    </div>
  );
}
