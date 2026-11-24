/** Types for the release-polish React feature. */

export type PolishSeverity = "blocker" | "major" | "minor" | "info";

export type PolishArea =
  | "Onboarding"
  | "Empty states"
  | "Design system"
  | "Iconography"
  | "Animation"
  | "Responsive";

export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  control: string;
  hint: string;
  required: boolean;
}

export interface EmptyStateSpec {
  surface: string;
  title: string;
  body: string;
  actionLabel: string;
  actionRoute: string;
  icon: string;
}

export interface ShowcaseEntry {
  token: string;
  label: string;
  kind: string;
  preview: string;
}

export interface IconLabel {
  icon: string;
  label: string;
  kind: string;
}

export interface AnimationAudit {
  surface: string;
  property: string;
  durationToken: string;
  reducedMotionSafe: boolean;
  note: string;
}

export interface PolishCheck {
  id: string;
  area: PolishArea;
  label: string;
  detail: string;
  severity: PolishSeverity;
  done: boolean;
}

export interface Breakpoint {
  name: string;
  width: number;
}

export interface ReleaseCounts {
  notes: number;
  findings: number;
  evidence: number;
  reports: number;
}

export interface ProgressSummary {
  total: number;
  done: number;
  required: number;
  requiredDone: number;
  percent: number;
}

export interface AnimationSummary {
  total: number;
  safe: number;
  unsafe: string[];
  percent: number;
}

export interface PolishSnapshot {
  onboarding: ProgressSummary;
  polish: ProgressSummary;
  animation: AnimationSummary;
  firstRun: string;
  breakpoint: string;
  labelIssues: number;
}

export interface ReleaseManifestData {
  version: string;
  namespace: string;
  actions: string[];
  phases: string[];
  scenarios: string[];
  frontend_surfaces: string[];
  offline_only: boolean;
  executes_user_code: boolean;
}
