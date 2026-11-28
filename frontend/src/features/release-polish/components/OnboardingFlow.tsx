/** Guided first-run onboarding flow. */

import { V3Panel } from "../../../v3/components/V3Panel";
import { nextOnboardingStep, onboardingProgress } from "../pure";
import type { OnboardingStep } from "../types";

export interface OnboardingFlowProps {
  steps: readonly OnboardingStep[];
  completed: readonly string[];
  onComplete: (step: string) => void;
  onSkip: () => void;
}

export function OnboardingFlow({
  steps,
  completed,
  onComplete,
  onSkip,
}: OnboardingFlowProps) {
  const progress = onboardingProgress(steps, completed);
  const active = nextOnboardingStep(steps, completed);

  return (
    <V3Panel
      title="First-run setup"
      subtitle={`${progress.done} of ${progress.total} steps complete`}
      kind="note"
    >
      <div
        className="release-onboarding"
        data-surface="onboarding-flow"
        aria-label="Onboarding"
      >
        <ol className="release-onboarding__steps" data-role="step-list">
          {steps.map((step, index) => {
            const done = completed.includes(step.id);
            return (
              <li
                className="release-onboarding__step"
                data-step={step.id}
                data-state={done ? "done" : "open"}
                key={step.id}
              >
                <span className="release-onboarding__index" aria-hidden="true">
                  {index + 1}
                </span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.description}</p>
                  <small>{step.hint}</small>
                </div>
                <button
                  aria-label={`Complete ${step.title}`}
                  className="release-v3-focusable"
                  data-action="complete-step"
                  disabled={done}
                  onClick={() => onComplete(step.id)}
                  type="button"
                >
                  {done ? "Done" : "Mark done"}
                </button>
              </li>
            );
          })}
        </ol>
        <footer
          className="release-onboarding__footer"
          data-role="onboarding-footer"
        >
          <span data-role="progress" aria-live="polite">
            Required {progress.requiredDone}/{progress.required}
          </span>
          <span data-role="next-step">
            {active?.title ?? "All required steps complete"}
          </span>
          <button
            aria-label="Skip optional onboarding steps"
            className="release-v3-focusable"
            data-action="skip-onboarding"
            onClick={onSkip}
            type="button"
          >
            Skip
          </button>
        </footer>
      </div>
    </V3Panel>
  );
}
