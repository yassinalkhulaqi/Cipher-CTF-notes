/** Reducer and selectors for the v4 accessibility panel. */

import type {
  AccessibilityStatus,
  AuditIssueView,
  MotionView,
  PatchResponse,
  PreferenceView,
  TourStateView,
  TourStepView,
} from "./client";

export type PanelTab = "controls" | "audit" | "tour" | "snapshots";

export interface AccessibilityState {
  status: AccessibilityStatus | null;
  theme: PreferenceView["theme"];
  density: PreferenceView["density"];
  motion: PreferenceView["motion"];
  locale: string;
  direction: "ltr" | "rtl";
  reduceMotion: boolean;
  highContrast: boolean;
  fontScale: number;
  previewDirection: "ltr" | "rtl";
  issues: AuditIssueView[];
  tour: TourStateView | null;
  tourStep: TourStepView | null;
  snapshots: string[];
  activeTab: PanelTab;
  busy: boolean;
  error: string | null;
  lastAction: string | null;
  lastSaved: string | null;
  dirty: boolean;
}

export type AccessibilityAction =
  | { type: "hydrate"; status: AccessibilityStatus }
  | { type: "set-theme"; theme: PreferenceView["theme"] }
  | { type: "set-density"; density: PreferenceView["density"] }
  | { type: "set-motion"; motion: PreferenceView["motion"] }
  | { type: "set-locale"; locale: string; direction?: "ltr" | "rtl" }
  | { type: "set-reduce-motion"; value: boolean }
  | { type: "set-high-contrast"; value: boolean }
  | { type: "set-font-scale"; value: number }
  | { type: "set-preview"; direction: "ltr" | "rtl" }
  | { type: "set-issues"; issues: AuditIssueView[] }
  | { type: "set-tour"; state: TourStateView; step: TourStepView }
  | { type: "set-snapshots"; names: string[] }
  | { type: "set-tab"; tab: PanelTab }
  | { type: "set-busy"; busy: boolean }
  | { type: "set-error"; error: string | null }
  | { type: "apply-response"; response: PatchResponse }
  | { type: "mark-saved"; name: string }
  | { type: "clear" };

const DEFAULT_PREFERENCES: PreferenceView = {
  theme: "light",
  density: "default",
  motion: "full",
  locale: "en",
  direction: "ltr",
  reduce_transparency: false,
  high_contrast: false,
  font_scale: 1,
};

export function initialAccessibilityState(): AccessibilityState {
  return {
    status: null,
    theme: DEFAULT_PREFERENCES.theme,
    density: DEFAULT_PREFERENCES.density,
    motion: DEFAULT_PREFERENCES.motion,
    locale: DEFAULT_PREFERENCES.locale,
    direction: DEFAULT_PREFERENCES.direction,
    reduceMotion: false,
    highContrast: false,
    fontScale: DEFAULT_PREFERENCES.font_scale,
    previewDirection: DEFAULT_PREFERENCES.direction,
    issues: [],
    tour: null,
    tourStep: null,
    snapshots: [],
    activeTab: "controls",
    busy: false,
    error: null,
    lastAction: null,
    lastSaved: null,
    dirty: false,
  };
}

export function hydrateStatus(
  state: AccessibilityState,
  status: AccessibilityStatus,
): AccessibilityState {
  return {
    ...state,
    status,
    theme: status.preferences.theme,
    density: status.preferences.density,
    motion: status.preferences.motion,
    locale: status.preferences.locale,
    direction: status.preferences.direction,
    reduceMotion: status.reduce_motion,
    highContrast: status.preferences.high_contrast,
    fontScale: status.preferences.font_scale,
    previewDirection: status.preferences.direction,
    tour: status.tour,
    tourStep: status.tour_step,
    snapshots: status.snapshots.names,
    error: null,
    dirty: false,
  };
}

export function accessibilityReducer(
  state: AccessibilityState,
  action: AccessibilityAction,
): AccessibilityState {
  switch (action.type) {
    case "hydrate":
      return hydrateStatus(state, action.status);
    case "set-theme":
      return { ...state, theme: action.theme, dirty: true };
    case "set-density":
      return { ...state, density: action.density, dirty: true };
    case "set-motion":
      return { ...state, motion: action.motion, dirty: true };
    case "set-locale":
      return {
        ...state,
        locale: action.locale,
        direction: action.direction ?? state.direction,
        previewDirection: action.direction ?? state.previewDirection,
        dirty: true,
      };
    case "set-reduce-motion":
      return { ...state, reduceMotion: action.value, dirty: true };
    case "set-high-contrast":
      return { ...state, highContrast: action.value, dirty: true };
    case "set-font-scale":
      return { ...state, fontScale: action.value, dirty: true };
    case "set-preview":
      return { ...state, previewDirection: action.direction };
    case "set-issues":
      return { ...state, issues: action.issues };
    case "set-tour":
      return { ...state, tour: action.state, tourStep: action.step };
    case "set-snapshots":
      return { ...state, snapshots: action.names };
    case "set-tab":
      return { ...state, activeTab: action.tab };
    case "set-busy":
      return { ...state, busy: action.busy };
    case "set-error":
      return { ...state, error: action.error, busy: false };
    case "apply-response":
      return {
        ...hydrateStatus(state, action.response.status),
        lastAction: action.response.action,
        dirty: false,
      };
    case "mark-saved":
      return {
        ...state,
        lastSaved: action.name,
        snapshots: [...new Set([...state.snapshots, action.name])].sort(),
      };
    case "clear":
      return initialAccessibilityState();
    default:
      return state;
  }
}

export function preferencePatch(
  state: AccessibilityState,
): Partial<PreferenceView> {
  return {
    theme: state.theme,
    density: state.density,
    motion: state.motion,
    locale: state.locale,
    direction: state.direction,
    reduce_transparency: state.reduceMotion,
    high_contrast: state.highContrast,
    font_scale: state.fontScale,
  };
}

const SEVERITY_RANK: Record<string, number> = { error: 2, warning: 1, info: 0 };

export function sortedIssues(issues: AuditIssueView[]): AuditIssueView[] {
  return [...issues].sort(
    (left, right) =>
      (SEVERITY_RANK[right.severity] ?? 0) -
        (SEVERITY_RANK[left.severity] ?? 0) ||
      left.fingerprint.localeCompare(right.fingerprint),
  );
}

export function issueSeverityCounts(
  issues: AuditIssueView[],
): Record<string, number> {
  const counts: Record<string, number> = { error: 0, warning: 0, info: 0 };
  for (const issue of issues) {
    counts[issue.severity] = (counts[issue.severity] ?? 0) + 1;
  }
  return counts;
}

export function motionLabel(motion: PreferenceView["motion"]): string {
  const labels: Record<PreferenceView["motion"], string> = {
    full: "Full motion",
    subtle: "Reduced motion",
    off: "No motion",
  };
  return labels[motion];
}

export function directionForLocale(
  directions: Record<string, string>,
  locale: string,
): "ltr" | "rtl" {
  return directions[locale] === "rtl" ? "rtl" : "ltr";
}

export function tourProgress(tour: TourStateView | null): number {
  if (!tour || tour.total === 0) return 0;
  return Math.round((tour.index / tour.total) * 100);
}

export function nextTourOperation(tour: TourStateView | null): string {
  if (!tour) return "start";
  if (tour.status === "not_started") return "start";
  if (tour.status === "completed" || tour.status === "skipped") return "reset";
  return "next";
}

export function issueCountLabel(count: number): string {
  return count === 1 ? "1 issue" : `${count} issues`;
}

export function canSaveSnapshot(
  state: AccessibilityState,
  name: string,
): boolean {
  return name.trim().length > 0 && !state.snapshots.includes(name.trim());
}

export function motionDurationLabel(motion: MotionView | null): string {
  if (!motion) return "—";
  return `${motion.durations.normal ?? 0}ms`;
}

export function statusSummary(status: AccessibilityStatus | null): string {
  if (!status) return "Loading accessibility status…";
  const localised = status.locales.length;
  const rules = status.rules.filter((rule) => rule.enabled).length;
  return `${rules} rules · ${localised} locales · ${status.snapshots.total} snapshots`;
}
