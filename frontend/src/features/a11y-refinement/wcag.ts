/** Client-side WCAG 2.2 rule metadata and audit helpers. */

import type {
  AuditRunView,
  AuditSummaryView,
  RuleFindingView,
  RuleInfo,
  Severity,
  SurfaceView,
  WcagLevel,
} from "./types";

export const WCAG22_RULES: RuleInfo[] = [
  rule("focus.not_obscured", "2.4.11", "Focus Not Obscured (Minimum)", "AA", "focus"),
  rule("focus.not_obscured.enhanced", "2.4.12", "Focus Not Obscured (Enhanced)", "AAA", "focus"),
  rule("focus.appearance", "2.4.13", "Focus Appearance", "AAA", "focus"),
  rule("pointer.dragging", "2.5.7", "Dragging Movements", "AA", "pointer"),
  rule("pointer.target_size", "2.5.8", "Target Size (Minimum)", "AA", "pointer"),
  rule("help.consistent", "3.2.6", "Consistent Help", "A", "document"),
  rule("form.redundant_entry", "3.3.7", "Redundant Entry", "A", "form"),
  rule("auth.accessible", "3.3.8", "Accessible Authentication", "AA", "form"),
  rule("auth.accessible.enhanced", "3.3.9", "Accessible Authentication (Enhanced)", "AAA", "form"),
  rule("contrast.non_text", "1.4.11", "Non-text Contrast", "AA", "content"),
  rule("content.hoverable", "1.4.13", "Content on Hover or Focus", "AA", "content"),
  rule("keyboard.reachable", "2.1.1", "Keyboard", "A", "focus"),
  rule("labels.screen_reader", "4.1.2", "Name, Role, Value", "A", "content"),
  rule("locale.direction", "3.1.1", "Language of Page", "A", "localization"),
];

const LEVEL_RANK: Record<WcagLevel, number> = { A: 1, AA: 2, AAA: 3 };
const SEVERITY_WEIGHT: Record<Severity, number> = {
  info: 0,
  minor: 1,
  moderate: 2,
  serious: 3,
  critical: 4,
};
const BLOCKING: Severity[] = ["moderate", "serious", "critical"];

function rule(
  id: string,
  criterion: string,
  title: string,
  level: WcagLevel,
  scope: string,
): RuleInfo {
  return {
    id,
    criterion,
    title,
    level,
    scope,
    description: `${title} (${criterion})`,
    remediation: `Review ${title.toLowerCase()} for this surface`,
    automated: true,
  };
}

export function rulesForLevel(level: WcagLevel): RuleInfo[] {
  const rank = LEVEL_RANK[level];
  return WCAG22_RULES.filter((item) => LEVEL_RANK[item.level] <= rank);
}

export function severityWeight(severity: Severity): number {
  return SEVERITY_WEIGHT[severity] ?? 0;
}

export function isBlocking(severity: Severity): boolean {
  return BLOCKING.includes(severity);
}

export function findingTone(severity: Severity): "neutral" | "warn" | "bad" {
  if (severity === "critical" || severity === "serious") return "bad";
  if (severity === "moderate") return "warn";
  return "neutral";
}

function finding(
  target: SurfaceView,
  id: string,
  severity: Severity,
  message: string,
  details: Record<string, unknown> = {},
): RuleFindingView {
  const spec = WCAG22_RULES.find((item) => item.id === id);
  return {
    rule: id,
    criterion: spec?.criterion ?? "",
    severity,
    target: target.name,
    message,
    remediation: spec?.remediation ?? "",
    details,
  };
}

function checks(surface: SurfaceView, level: WcagLevel): RuleFindingView[] {
  const findings: RuleFindingView[] = [];
  const eligible = new Set(rulesForLevel(level).map((item) => item.id));
  const add = (
    id: string,
    enabled: boolean,
    severity: Severity,
    message: string,
    details: Record<string, unknown> = {},
  ): void => {
    if (enabled && eligible.has(id)) findings.push(finding(surface, id, severity, message, details));
  };
  add(
    "keyboard.reachable",
    !surface.keyboard_reachable,
    "critical",
    `${surface.name} is not fully keyboard reachable`,
  );
  add(
    "labels.screen_reader",
    !surface.screen_reader_labels,
    "serious",
    `${surface.name} has unlabeled controls`,
  );
  add(
    "focus.not_obscured",
    ["partial", "full", "fully"].includes(surface.focus_obscured),
    "serious",
    `Focus is ${surface.focus_obscured} obscured on ${surface.name}`,
    { state: surface.focus_obscured },
  );
  add(
    "focus.not_obscured.enhanced",
    ["full", "fully"].includes(surface.focus_obscured),
    "moderate",
    "Part of the focused control is hidden",
  );
  add(
    "focus.appearance",
    surface.focus_indicator_width < 2,
    "serious",
    `Focus indicator is ${surface.focus_indicator_width}px`,
    { width: surface.focus_indicator_width },
  );
  add(
    "pointer.dragging",
    surface.drag_only,
    "serious",
    `${surface.name} requires dragging without an alternative`,
  );
  add(
    "pointer.target_size",
    surface.target_size < 24,
    surface.target_size < 12 ? "serious" : "moderate",
    `Target size is ${surface.target_size}px`,
    { size: surface.target_size },
  );
  add(
    "contrast.non_text",
    surface.non_text_contrast < 3,
    surface.non_text_contrast < 2 ? "serious" : "moderate",
    `Non-text contrast is ${surface.non_text_contrast.toFixed(2)}:1`,
    { ratio: surface.non_text_contrast },
  );
  add("content.hoverable", surface.hover_content, "moderate", "Hover content may disappear");
  add("help.consistent", !surface.has_help, "minor", "Help is missing from this surface");
  add("form.redundant_entry", surface.repeated_entry, "moderate", "A value is requested twice");
  add(
    "auth.accessible",
    ["captcha", "puzzle", "cognitive"].includes(surface.auth_captcha),
    "serious",
    `Authentication uses ${surface.auth_captcha}`,
  );
  add(
    "auth.accessible.enhanced",
    ["puzzle", "cognitive", "object_recognition"].includes(surface.auth_captcha),
    "moderate",
    "Authentication requires a cognitive function test",
  );
  add(
    "locale.direction",
    /^[a-z]{2}$/i.test(surface.locale) === false,
    "moderate",
    `Invalid language tag: ${surface.locale}`,
  );
  return findings;
}

export function auditSurface(surface: SurfaceView, level: WcagLevel = surface.level): AuditRunView {
  const findings = checks(surface, level).sort(
    (first, second) => severityWeight(second.severity) - severityWeight(first.severity),
  );
  const eligible = rulesForLevel(level);
  const fired = new Set(findings.map((item) => item.rule));
  const penalty = findings.reduce((total, item) => total + Math.max(1, severityWeight(item.severity) * 2), 0);
  return {
    surface: surface.name,
    level,
    findings,
    passed_rules: eligible.filter((item) => !fired.has(item.id)).map((item) => item.id),
    checked: eligible.length,
    score: Math.max(0, 100 - penalty),
    passed: !findings.some((item) => isBlocking(item.severity)),
  };
}

export function summarizeAudits(runs: AuditRunView[]): AuditSummaryView {
  const findings = runs.flatMap((run) => run.findings);
  const bySeverity: Record<string, number> = {};
  for (const item of findings) {
    bySeverity[item.severity] = (bySeverity[item.severity] ?? 0) + 1;
  }
  const score = runs.length
    ? runs.reduce((sum, run) => sum + run.score, 0) / runs.length
    : 100;
  return {
    surfaces: runs.length,
    passed: runs.filter((run) => run.passed).length,
    failed: runs.filter((run) => !run.passed).length,
    findings: findings.length,
    by_severity: bySeverity,
    checked_rules: runs.reduce((sum, run) => sum + run.checked, 0),
    score: Math.round(score * 10) / 10,
    criteria: [...new Set(findings.map((item) => item.criterion))].sort(),
  };
}

export function filterFindings(runs: AuditRunView[], level: Severity | "all"): RuleFindingView[] {
  return runs.flatMap((run) =>
    run.findings.filter((item) => level === "all" || item.severity === level),
  );
}

export function scoreTone(score: number): "good" | "warn" | "bad" {
  if (score >= 90) return "good";
  if (score >= 60) return "warn";
  return "bad";
}
