/** Relationship editing gestures, undo/redo, and snapshot controls. */

import type { GestureState } from "./editor";
import { canCommit, describeGesture } from "./editor";
import type { EditRecord } from "./types";
import { LINK_KINDS } from "./types";

export interface RelationshipPanelProps {
  gesture: GestureState;
  historyText: string;
  canUndo: boolean;
  canRedo: boolean;
  busy?: boolean;
  onKind: (kind: string) => void;
  onLabel: (label: string) => void;
  onWeight: (weight: number) => void;
  onCommit: () => void;
  onCancel: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onSnapshot: () => void;
  lastRecord?: EditRecord | null;
}

export function RelationshipPanel({
  gesture,
  historyText,
  canUndo,
  canRedo,
  busy = false,
  onKind,
  onLabel,
  onWeight,
  onCommit,
  onCancel,
  onUndo,
  onRedo,
  onSnapshot,
  lastRecord,
}: RelationshipPanelProps) {
  return (
    <section className="gw-relationships" data-testid="gw-relationship-panel">
      <header className="gw-section-header">
        <h3>Relationships</h3>
        <span className="gw-section-hint">Click two nodes to connect them</span>
      </header>
      <p
        className="gw-gesture-status"
        data-phase={gesture.phase}
        data-testid="gw-gesture-status"
      >
        {describeGesture(gesture)}
      </p>
      <div className="gw-relationships__form">
        <label>
          <span>Kind</span>
          <select
            value={gesture.draft.kind}
            data-testid="gw-relation-kind"
            aria-label="Relationship kind"
            onChange={(event) => onKind(event.target.value)}
          >
            {LINK_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Label</span>
          <input
            type="text"
            value={gesture.draft.label}
            maxLength={80}
            data-testid="gw-relation-label"
            aria-label="Relationship label"
            placeholder="optional description"
            onChange={(event) => onLabel(event.target.value)}
          />
        </label>
        <label className="gw-weight">
          <span>Weight {gesture.draft.weight.toFixed(2)}</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={gesture.draft.weight}
            data-testid="gw-relation-weight"
            aria-label="Relationship weight"
            onChange={(event) => onWeight(Number(event.target.value))}
          />
        </label>
      </div>
      <div className="gw-relationships__actions">
        <button
          type="button"
          className="gw-primary"
          data-testid="gw-relation-commit"
          disabled={!canCommit(gesture) || busy}
          onClick={onCommit}
        >
          Connect
        </button>
        <button
          type="button"
          data-testid="gw-relation-cancel"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          type="button"
          data-testid="gw-relation-undo"
          disabled={!canUndo}
          onClick={onUndo}
        >
          Undo
        </button>
        <button
          type="button"
          data-testid="gw-relation-redo"
          disabled={!canRedo}
          onClick={onRedo}
        >
          Redo
        </button>
        <button
          type="button"
          data-testid="gw-relation-snapshot"
          onClick={onSnapshot}
        >
          Snapshot
        </button>
      </div>
      <p className="gw-history" data-testid="gw-history">
        {historyText}
        {lastRecord ? ` · #${lastRecord.sequence} ${lastRecord.action}` : ""}
      </p>
    </section>
  );
}
