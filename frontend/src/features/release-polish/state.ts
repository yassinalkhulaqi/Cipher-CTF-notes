/** Local UI state for the release-polish feature. */

import { GOLDEN_PHASES, ONBOARDING_STEPS, POLISH_CHECKS } from "./config";
import { isOnboardingComplete, nextOnboardingStep, polishProgress } from "./pure";

export interface ReleasePolishState {
  completed: string[];
  dismissed: string[];
  checked: string[];
  selectedSurface: string;
  selectedArea: string;
  selectedPhase: string;
  width: number;
}

export type ReleasePolishAction =
  | { type: "complete"; step: string }
  | { type: "dismiss"; surface: string }
  | { type: "toggle-check"; check: string }
  | { type: "select-surface"; surface: string }
  | { type: "select-area"; area: string }
  | { type: "select-phase"; phase: string }
  | { type: "resize"; width: number }
  | { type: "reset" };

export function initialReleasePolishState(width = 1280): ReleasePolishState {
  return {
    completed: [],
    dismissed: [],
    checked: POLISH_CHECKS.filter((check) => check.done).map((check) => check.id),
    selectedSurface: "notes",
    selectedArea: "All",
    selectedPhase: GOLDEN_PHASES[0] ?? "capture",
    width,
  };
}

export function releasePolishReducer(
  state: ReleasePolishState,
  action: ReleasePolishAction,
): ReleasePolishState {
  switch (action.type) {
    case "complete":
      if (state.completed.includes(action.step)) return state;
      return { ...state, completed: [...state.completed, action.step] };
    case "dismiss":
      if (state.dismissed.includes(action.surface)) return state;
      return { ...state, dismissed: [...state.dismissed, action.surface] };
    case "toggle-check": {
      const exists = state.checked.includes(action.check);
      return {
        ...state,
        checked: exists
          ? state.checked.filter((item) => item !== action.check)
          : [...state.checked, action.check],
      };
    }
    case "select-surface":
      return { ...state, selectedSurface: action.surface };
    case "select-area":
      return { ...state, selectedArea: action.area };
    case "select-phase":
      return GOLDEN_PHASES.includes(action.phase)
        ? { ...state, selectedPhase: action.phase }
        : state;
    case "resize":
      return { ...state, width: Math.max(0, action.width) };
    case "reset":
      return initialReleasePolishState(state.width);
  }
}

export function activeStep(state: ReleasePolishState): string {
  return nextOnboardingStep(ONBOARDING_STEPS, state.completed)?.id ?? "";
}

export function completionLabel(state: ReleasePolishState): string {
  return isOnboardingComplete(ONBOARDING_STEPS, state.completed) ? "Ready" : "In progress";
}

export function polishLabel(state: ReleasePolishState): string {
  const progress = polishProgress(
    POLISH_CHECKS.map((check) => ({ ...check, done: state.checked.includes(check.id) })),
  );
  return `${progress.done}/${progress.total}`;
}
