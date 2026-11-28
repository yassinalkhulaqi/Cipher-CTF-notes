/** Reducer and selectors for the portability feature workbench. */

import {
  advanceWizard,
  applyResolution,
  buildWizardSteps,
  defaultPlan,
  unresolvedCount,
} from "./pure";
import type { PortabilityAction, PortabilityState } from "./types";

export function initialPortabilityState(): PortabilityState {
  return {
    plan: defaultPlan(),
    wizard: buildWizardSteps(),
    stepIndex: 0,
    dryRun: null,
    conflicts: [],
    vector: null,
    progress: null,
    receipt: null,
    audit: [],
    busy: false,
    notice: null,
  };
}

export function portabilityReducer(
  state: PortabilityState,
  action: PortabilityAction,
): PortabilityState {
  switch (action.type) {
    case "plan":
      return { ...state, plan: { ...state.plan, ...action.value } };
    case "step":
      return {
        ...state,
        stepIndex: action.index,
        wizard: advanceWizard(state.wizard, action.index, action.status),
      };
    case "dry-run":
      return {
        ...state,
        dryRun: action.value,
        conflicts: action.value ? action.value.conflicts : state.conflicts,
      };
    case "conflicts":
      return { ...state, conflicts: action.value };
    case "resolve":
      return {
        ...state,
        conflicts: applyResolution(
          state.conflicts,
          action.ref,
          action.resolution,
        ),
      };
    case "vector":
      return { ...state, vector: action.value };
    case "progress":
      return { ...state, progress: action.value };
    case "receipt":
      return { ...state, receipt: action.value };
    case "audit":
      return { ...state, audit: action.value };
    case "busy":
      return { ...state, busy: action.value };
    case "notice":
      return { ...state, notice: action.value };
    case "reset":
      return initialPortabilityState();
    default:
      return state;
  }
}

export function selectReadyToRun(state: PortabilityState): boolean {
  if (state.busy) return false;
  if (!state.dryRun) return false;
  return unresolvedCount(state.conflicts) === 0;
}

export function selectUnresolved(state: PortabilityState): number {
  return unresolvedCount(state.conflicts);
}

export function selectReceipt(state: PortabilityState) {
  return state.receipt;
}

export function selectProgress(state: PortabilityState) {
  return state.progress;
}

export function selectStep(state: PortabilityState) {
  return state.wizard[state.stepIndex] ?? null;
}

export function selectNotice(state: PortabilityState) {
  return state.notice;
}
