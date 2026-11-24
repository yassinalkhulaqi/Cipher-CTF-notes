/** Top-level release-polish feature surface. */

import { useReducer } from "react";

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { GOLDEN_PHASES, ONBOARDING_STEPS, RELEASE_SURFACES } from "./config";
import { formatPercent, releaseSnapshot } from "./pure";
import {
  initialReleasePolishState,
  releasePolishReducer,
} from "./state";
import type { ReleaseCounts } from "./types";
import { AnimationAuditView } from "./components/AnimationAuditView";
import { DesignSystemShowcase } from "./components/DesignSystemShowcase";
import { EmptyAndFirstRun } from "./components/EmptyAndFirstRun";
import { IconographyAudit } from "./components/IconographyAudit";
import { OnboardingFlow } from "./components/OnboardingFlow";
import { ResponsivePolishChecklist } from "./components/ResponsivePolishChecklist";

export interface ReleasePolishFeatureProps {
  counts?: ReleaseCounts;
  reducedMotion?: boolean;
  width?: number;
}

const EMPTY_COUNTS: ReleaseCounts = { notes: 0, findings: 0, evidence: 0, reports: 0 };

export function ReleasePolishFeature({
  counts = EMPTY_COUNTS,
  reducedMotion = false,
  width = 1280,
}: ReleasePolishFeatureProps) {
  const [state, dispatch] = useReducer(
    releasePolishReducer,
    width,
    initialReleasePolishState,
  );
  const snapshot = releaseSnapshot(state.completed, state.checked, counts, state.width);

  return (
    <section
      className="release-polish"
      data-feature="release-polish"
      data-phase={state.selectedPhase}
      aria-label="Release polish"
    >
      <V3Panel
        title="Release readiness"
        subtitle="Golden paths, polish, and first-run experience"
        kind="report"
      >
        <div className="release-polish__stats" data-role="release-stats">
          <V3Stat
            label="Onboarding"
            value={formatPercent(snapshot.onboarding.percent)}
            hint={`${snapshot.onboarding.done}/${snapshot.onboarding.total}`}
          />
          <V3Stat
            label="Polish"
            value={formatPercent(snapshot.polish.percent)}
            hint={`${snapshot.polish.done}/${snapshot.polish.total}`}
            tone="good"
          />
          <V3Stat
            label="Motion"
            value={formatPercent(snapshot.animation.percent)}
            hint={snapshot.animation.unsafe.length ? "review open items" : "all safe"}
          />
          <V3Stat label="First run" value={snapshot.firstRun} hint={snapshot.breakpoint} />
        </div>
        <div className="release-polish__phases" data-role="phase-strip">
          {GOLDEN_PHASES.map((phase, index) => (
            <button
              aria-label={`Inspect ${phase} phase`}
              aria-pressed={state.selectedPhase === phase}
              className="release-v3-focusable"
              data-action="select-phase"
              data-phase={phase}
              key={phase}
              onClick={() => dispatch({ type: "select-phase", phase })}
              type="button"
            >
              {index + 1}. {phase}
            </button>
          ))}
        </div>
        <p className="release-polish__surfaces" data-role="surface-list">
          Surfaces: {RELEASE_SURFACES.join(" · ")}
        </p>
      </V3Panel>

      <div className="release-polish__grid" data-role="feature-grid">
        <OnboardingFlow
          steps={ONBOARDING_STEPS}
          completed={state.completed}
          onComplete={(step) => dispatch({ type: "complete", step })}
          onSkip={() => dispatch({ type: "dismiss", surface: "onboarding" })}
        />
        <EmptyAndFirstRun
          counts={counts}
          surface={state.selectedSurface}
          dismissed={state.dismissed}
          onAction={(route) => dispatch({ type: "select-surface", surface: route })}
          onDismiss={(surface) => dispatch({ type: "dismiss", surface })}
        />
        <DesignSystemShowcase
          density={state.width < 768 ? "compact" : "comfortable"}
          onDensityChange={(value) =>
            dispatch({ type: "resize", width: value === "compact" ? 480 : 1280 })
          }
        />
        <IconographyAudit />
        <AnimationAuditView reducedMotion={reducedMotion} />
        <ResponsivePolishChecklist
          checked={state.checked}
          width={state.width}
          selectedArea={state.selectedArea}
          onToggle={(check) => dispatch({ type: "toggle-check", check })}
          onAreaChange={(area) => dispatch({ type: "select-area", area })}
        />
      </div>
    </section>
  );
}

export default ReleasePolishFeature;
