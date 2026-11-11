import { CircleDot, Flag, Target } from "lucide-react";
import { AnimatedNumber } from "../../motion/AnimatedNumber";

export interface PulseStripProps {
  noteCount: number;
  activeCount: number;
  doneCount: number;
  flaggedCount: number;
  targets: Array<[string, number]>;
  flagTotal: number;
  onFilterAll: () => void;
  onShowDashboard: () => void;
  onFlagIntel: () => void;
  onFilterTarget: (target: string) => void;
}

/** Top-of-dashboard statistics strip (notes / active / flags / targets). */
export function PulseStrip({
  noteCount,
  activeCount,
  doneCount,
  flaggedCount,
  targets,
  flagTotal,
  onFilterAll,
  onShowDashboard,
  onFlagIntel,
  onFilterTarget,
}: PulseStripProps) {
  return (
    <div className="pulse-strip" aria-label="Vault statistics" data-reveal>
      <button type="button" className="pulse-cell" onClick={onFilterAll}>
        <span className="pulse-label">Total notes</span>
        <strong>
          <AnimatedNumber value={noteCount} />
        </strong>
        <span className="pulse-note">
          <CircleDot /> {activeCount} active
        </span>
      </button>
      <button
        type="button"
        className="pulse-cell"
        onClick={onShowDashboard}
      >
        <span className="pulse-label">Active challenges</span>
        <strong>
          <AnimatedNumber value={activeCount} />
        </strong>
        <span className="pulse-note">
          <CircleDot /> {doneCount} completed
        </span>
      </button>
      <button type="button" className="pulse-cell" onClick={onFlagIntel}>
        <span className="pulse-label">Captured flags</span>
        <strong className="green">
          <AnimatedNumber value={flagTotal} />
        </strong>
        <span className="pulse-note">
          <Flag /> {flaggedCount} manual
        </span>
      </button>
      <button
        type="button"
        className="pulse-cell"
        onClick={() => {
          const target = targets[0]?.[0];
          if (target) onFilterTarget(target);
        }}
      >
        <span className="pulse-label">Targets</span>
        <strong>
          <AnimatedNumber value={targets.length} />
        </strong>
        <span className="pulse-note">
          <Target /> {targets[0]?.[0] ?? "none yet"}
        </span>
      </button>
    </div>
  );
}
