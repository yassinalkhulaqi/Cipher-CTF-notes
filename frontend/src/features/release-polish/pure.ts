/** Pure helpers for the release-polish feature. */

import {
  ANIMATION_AUDITS,
  BREAKPOINTS,
  EMPTY_STATES,
  KIND_LABELS,
  MOTION_TOKENS,
  ONBOARDING_STEPS,
  POLISH_CHECKS,
} from "./config";
import type {
  AnimationAudit,
  AnimationSummary,
  Breakpoint,
  EmptyStateSpec,
  IconLabel,
  OnboardingStep,
  PolishArea,
  PolishCheck,
  PolishSnapshot,
  ProgressSummary,
  ReleaseCounts,
  ShowcaseEntry,
} from "./types";

export function formatPercent(value: number): string {
  const bounded = Math.max(0, Math.min(100, Math.round(value)));
  return `${bounded}%`;
}

export function onboardingProgress(
  steps: readonly OnboardingStep[] = ONBOARDING_STEPS,
  completed: readonly string[] = [],
): ProgressSummary {
  const doneSet = new Set(completed);
  const required = steps.filter((step) => step.required);
  const requiredDone = required.filter((step) => doneSet.has(step.id)).length;
  const done = steps.filter((step) => doneSet.has(step.id)).length;
  return {
    total: steps.length,
    done,
    required: required.length,
    requiredDone,
    percent: steps.length === 0 ? 100 : (done / steps.length) * 100,
  };
}

export function nextOnboardingStep(
  steps: readonly OnboardingStep[] = ONBOARDING_STEPS,
  completed: readonly string[] = [],
): OnboardingStep | undefined {
  const doneSet = new Set(completed);
  return (
    steps.find((step) => step.required && !doneSet.has(step.id)) ??
    steps.find((step) => !doneSet.has(step.id))
  );
}

export function isOnboardingComplete(
  steps: readonly OnboardingStep[] = ONBOARDING_STEPS,
  completed: readonly string[] = [],
): boolean {
  const doneSet = new Set(completed);
  return steps.filter((step) => step.required).every((step) => doneSet.has(step.id));
}

export function emptyStateFor(
  surface: string,
  specs: readonly EmptyStateSpec[] = EMPTY_STATES,
): EmptyStateSpec | undefined {
  return specs.find((spec) => spec.surface === surface);
}

export function firstRunState(
  counts: ReleaseCounts,
  specs: readonly EmptyStateSpec[] = EMPTY_STATES,
): EmptyStateSpec | undefined {
  if (counts.notes === 0) return emptyStateFor("notes", specs);
  if (counts.findings === 0) return emptyStateFor("findings", specs);
  if (counts.evidence === 0) return emptyStateFor("evidence", specs);
  if (counts.reports === 0) return emptyStateFor("report", specs);
  return undefined;
}

export function firstRunSurface(
  counts: ReleaseCounts,
  specs: readonly EmptyStateSpec[] = EMPTY_STATES,
): string {
  return firstRunState(counts, specs)?.surface ?? "ready";
}

export function showcaseByKind(
  entries: readonly ShowcaseEntry[],
  kind: string,
): ShowcaseEntry[] {
  return entries.filter((entry) => entry.kind === kind);
}

export function showcaseTokens(entries: readonly ShowcaseEntry[]): string[] {
  return Array.from(new Set(entries.map((entry) => entry.token))).sort();
}

export function kindColorToken(kind: string): string {
  return `var(--v3-kind-${kind}, var(--v3-kind-default))`;
}

export function iconForKind(icons: readonly IconLabel[], kind: string): string | undefined {
  return icons.find((entry) => entry.kind === kind)?.icon;
}

export function labelForKind(kind: string, labels: Record<string, string> = KIND_LABELS): string {
  return labels[kind] ?? kind.replace(/(^|-)([a-z])/g, (_match, _sep, letter: string) => letter.toUpperCase());
}

export function labelConsistencyIssues(
  icons: readonly IconLabel[],
  labels: Record<string, string> = KIND_LABELS,
): string[] {
  return icons
    .filter((entry) => labels[entry.kind] !== entry.label)
    .map((entry) => `${entry.kind}: expected ${labels[entry.kind] ?? "unknown"}, got ${entry.label}`);
}

export function auditAnimations(audits: readonly AnimationAudit[] = ANIMATION_AUDITS): AnimationSummary {
  const unsafe = audits.filter((audit) => !audit.reducedMotionSafe).map((audit) => audit.surface);
  return {
    total: audits.length,
    safe: audits.length - unsafe.length,
    unsafe,
    percent: audits.length === 0 ? 100 : ((audits.length - unsafe.length) / audits.length) * 100,
  };
}

export function usesMotionToken(token: string): boolean {
  return MOTION_TOKENS.includes(token);
}

export function animationsWithInvalidTokens(audits: readonly AnimationAudit[]): string[] {
  return audits.filter((audit) => !usesMotionToken(audit.durationToken)).map((audit) => audit.surface);
}

export function polishProgress(
  checks: readonly PolishCheck[] = POLISH_CHECKS,
): ProgressSummary {
  const done = checks.filter((check) => check.done).length;
  return {
    total: checks.length,
    done,
    required: checks.filter((check) => check.severity === "blocker").length,
    requiredDone: checks.filter((check) => check.severity === "blocker" && check.done).length,
    percent: checks.length === 0 ? 100 : (done / checks.length) * 100,
  };
}

export function filterPolishByArea(
  checks: readonly PolishCheck[],
  area: PolishArea | "All",
): PolishCheck[] {
  return area === "All" ? [...checks] : checks.filter((check) => check.area === area);
}

export function polishAreas(checks: readonly PolishCheck[] = POLISH_CHECKS): PolishArea[] {
  return Array.from(new Set(checks.map((check) => check.area)));
}

export function withCheckState(
  checks: readonly PolishCheck[],
  checked: readonly string[],
): PolishCheck[] {
  const overrides = new Set(checked);
  return checks.map((check) =>
    overrides.has(check.id)
      ? check
      : { ...check, done: false },
  );
}

export function resolveBreakpoint(
  width: number,
  breakpoints: readonly Breakpoint[] = BREAKPOINTS,
): string {
  const sorted = [...breakpoints].sort((left, right) => left.width - right.width);
  let name = sorted[0]?.name ?? "narrow";
  for (const breakpoint of sorted) {
    if (width >= breakpoint.width) name = breakpoint.name;
  }
  return name;
}

export function responsiveRisk(breakpoint: string): "low" | "medium" | "high" {
  if (breakpoint === "narrow") return "high";
  if (breakpoint === "medium") return "medium";
  return "low";
}

export function releaseSnapshot(
  completed: readonly string[],
  checked: readonly string[],
  counts: ReleaseCounts,
  width: number,
): PolishSnapshot {
  const checks = withCheckState(POLISH_CHECKS, checked);
  const breakpoint = resolveBreakpoint(width);
  return {
    onboarding: onboardingProgress(ONBOARDING_STEPS, completed),
    polish: polishProgress(checks),
    animation: auditAnimations(ANIMATION_AUDITS),
    firstRun: firstRunSurface(counts),
    breakpoint,
    labelIssues: labelConsistencyIssues(
      [
        { icon: "file-text", label: "Note", kind: "note" },
        { icon: "alert", label: "Finding", kind: "finding" },
      ],
      KIND_LABELS,
    ).length,
  };
}

/** Alias used by consumers that only need the safe-surface count. */
export function auditsSafeCount(audits: readonly AnimationAudit[] = ANIMATION_AUDITS): number {
  return auditAnimations(audits).safe;
}

/** Alias for callers that prefer a verb-led name. */
export const animationSummarySafe = auditAnimations;
