/** Guided, keyboard-driven step runner state machine. */

import { compileDag, nextReady } from "./dag";
import type { StepDef } from "./types";

export type RunnerAction =
  | { type: "next" }
  | { type: "previous" }
  | { type: "toggle" }
  | { type: "jump"; stepId: string }
  | { type: "first" }
  | { type: "last" }
  | { type: "reset" };

export interface RunnerState {
  order: string[];
  completed: string[];
  cursor: number;
  steps: StepDef[];
}

export function createRunner(steps: StepDef[]): RunnerState {
  const compilation = compileDag(steps);
  const order = compilation.ok
    ? compilation.order
    : steps.map((step) => step.id);
  return { order, completed: [], cursor: 0, steps };
}

function clamp(value: number, maximum: number): number {
  return Math.max(0, Math.min(value, maximum));
}

export function runnerReducer(
  state: RunnerState,
  action: RunnerAction,
): RunnerState {
  if (action.type === "reset") return createRunner(state.steps);
  if (action.type === "first") return { ...state, cursor: 0 };
  if (action.type === "last")
    return {
      ...state,
      cursor: clamp(state.order.length - 1, state.order.length - 1),
    };
  if (action.type === "jump") {
    const index = state.order.indexOf(action.stepId);
    return index < 0 ? state : { ...state, cursor: index };
  }
  const current = state.order[state.cursor] ?? "";
  if (action.type === "toggle") {
    if (!current || state.completed.includes(current)) return state;
    const graph = Object.fromEntries(
      state.steps.map((step) => [step.id, step.depends_on ?? []]),
    );
    const ready = nextReady(state.order, graph, state.completed);
    if (!ready.includes(current)) return state;
    const completed = [...state.completed, current];
    const cursor = clamp(state.cursor + 1, state.order.length - 1);
    return { ...state, completed, cursor };
  }
  if (action.type === "next") {
    if (current && !state.completed.includes(current)) {
      const graph = Object.fromEntries(
        state.steps.map((step) => [step.id, step.depends_on ?? []]),
      );
      if (nextReady(state.order, graph, state.completed).includes(current)) {
        const completed = [...state.completed, current];
        return {
          ...state,
          completed,
          cursor: clamp(state.cursor + 1, state.order.length - 1),
        };
      }
    }
    return {
      ...state,
      cursor: clamp(state.cursor + 1, state.order.length - 1),
    };
  }
  return { ...state, cursor: clamp(state.cursor - 1, state.order.length - 1) };
}

export const RUNNER_KEYS: Record<string, RunnerAction["type"]> = {
  ArrowRight: "next",
  ArrowLeft: "previous",
  " ": "toggle",
  Enter: "toggle",
  Home: "first",
  End: "last",
};

export function actionForKey(key: string): RunnerAction | null {
  switch (key) {
    case "ArrowRight":
      return { type: "next" };
    case "ArrowLeft":
      return { type: "previous" };
    case " ":
    case "Enter":
      return { type: "toggle" };
    case "Home":
      return { type: "first" };
    case "End":
      return { type: "last" };
    default:
      return null;
  }
}

export function runnerProgress(state: RunnerState): {
  done: number;
  total: number;
  percent: number;
} {
  const total = state.order.length;
  const done = state.completed.length;
  return { done, total, percent: total ? Math.round((done / total) * 100) : 0 };
}

export function currentStep(state: RunnerState): StepDef | null {
  const id = state.order[state.cursor];
  return state.steps.find((step) => step.id === id) ?? null;
}
