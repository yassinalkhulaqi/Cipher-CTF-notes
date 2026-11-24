/** Guided keyboard step runner. */

import { useReducer } from "react";
import {
  actionForKey,
  createRunner,
  currentStep,
  runnerProgress,
  runnerReducer,
} from "./runner";
import type { StepDef } from "./types";
import { STEP_LABELS } from "./types";

export interface StepRunnerProps {
  steps: StepDef[];
}

export function StepRunner({ steps }: StepRunnerProps) {
  const [state, dispatch] = useReducer(runnerReducer, steps, createRunner);
  const progress = runnerProgress(state);
  const step = currentStep(state);

  return (
    <div
      className="automation-runner"
      data-automation="step-runner"
      tabIndex={0}
      role="group"
      aria-label="Guided step runner. Use arrow keys to move, space to mark a step done."
      onKeyDown={(event) => {
        const action = actionForKey(event.key);
        if (action) {
          event.preventDefault();
          dispatch(action);
        }
      }}
    >
      <div
        className="automation-runner__progress"
        data-automation="runner-progress"
        data-percent={progress.percent}
      >
        <span>
          {progress.done}/{progress.total} steps
        </span>
        <div className="automation-runner__bar">
          <i style={{ width: `${progress.percent}%` }} />
        </div>
      </div>
      {step ? (
        <div
          className="automation-runner__current"
          data-automation="runner-current"
          data-step-id={step.id}
        >
          <span className="automation-runner__index">{state.cursor + 1}</span>
          <div>
            <strong>{step.title}</strong>
            <span>{STEP_LABELS[step.kind]}</span>
            <span>
              depends on: {(step.depends_on ?? []).join(", ") || "none"}
            </span>
          </div>
        </div>
      ) : (
        <p>Add a step to begin the guided run.</p>
      )}
      <div className="automation-runner__controls">
        <button
          type="button"
          data-automation="runner-previous"
          onClick={() => dispatch({ type: "previous" })}
        >
          Previous
        </button>
        <button
          type="button"
          data-automation="runner-toggle"
          onClick={() => dispatch({ type: "toggle" })}
        >
          Mark done
        </button>
        <button
          type="button"
          data-automation="runner-next"
          onClick={() => dispatch({ type: "next" })}
        >
          Next
        </button>
        <button
          type="button"
          data-automation="runner-reset"
          onClick={() => dispatch({ type: "reset" })}
        >
          Reset
        </button>
      </div>
      <p className="automation-runner__hint">
        Arrow keys navigate · Space/Enter marks done · Home/End jump
      </p>
    </div>
  );
}
