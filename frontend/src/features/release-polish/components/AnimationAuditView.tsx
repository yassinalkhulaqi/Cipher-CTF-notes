/** Motion and reduced-motion audit view. */

import { V3Panel, V3Stat } from "../../../v3/components/V3Panel";
import { ANIMATION_AUDITS } from "../config";
import {
  animationsWithInvalidTokens,
  auditAnimations,
  formatPercent,
} from "../pure";

export interface AnimationAuditViewProps {
  reducedMotion: boolean;
}

export function AnimationAuditView({ reducedMotion }: AnimationAuditViewProps) {
  const summary = auditAnimations(ANIMATION_AUDITS);
  const invalidTokens = animationsWithInvalidTokens(ANIMATION_AUDITS);
  return (
    <V3Panel
      title="Animation audit"
      subtitle={reducedMotion ? "Reduced motion active" : "Full motion active"}
      kind="activity"
    >
      <div
        className="release-motion"
        data-surface="animation-audit"
        data-reduced-motion={reducedMotion}
        aria-label="Animation audit"
      >
        <div className="release-motion__stats" data-role="motion-stats">
          <V3Stat
            label="Safe surfaces"
            value={`${summary.safe}/${summary.total}`}
            tone="good"
          />
          <V3Stat label="Coverage" value={formatPercent(summary.percent)} />
          <V3Stat
            label="Open items"
            value={summary.unsafe.length + invalidTokens.length}
            tone={summary.unsafe.length > 0 ? "warn" : "neutral"}
          />
        </div>
        <button
          aria-label="Review animation audit findings"
          className="release-v3-focusable"
          data-action="review-motion"
          type="button"
        >
          Review findings
        </button>
        <ul className="release-motion__list" data-role="motion-list">
          {ANIMATION_AUDITS.map((audit) => (
            <li
              className="release-motion__item"
              data-surface-name={audit.surface}
              data-safe={audit.reducedMotionSafe}
              key={audit.surface}
            >
              <code>{audit.durationToken}</code>
              <span>{audit.surface}</span>
              <span>{audit.property}</span>
              <span
                aria-label={
                  audit.reducedMotionSafe
                    ? "Reduced motion safe"
                    : "Needs fallback"
                }
              >
                {audit.reducedMotionSafe ? "safe" : "needs fallback"}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </V3Panel>
  );
}
