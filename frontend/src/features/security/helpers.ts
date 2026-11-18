import type {
  AuditFinding,
  AuditReport,
  CommandSafety,
  ConsentSummary,
  PolicyEvaluation,
  PrivacyControl,
  PrivacyMode,
  RedactionSummary,
  RiskAssessment,
  SecretFinding,
  SecretScanResult,
  SecurityDashboard,
  Severity,
  UrlSafety,
} from "./types";

export const SEVERITY_RANK: Record<Severity, number> = {
  none: 0,
  info: 1,
  low: 2,
  medium: 3,
  high: 4,
  critical: 5,
};

export const SEVERITY_COLORS: Record<Severity, string> = {
  none: "var(--text-muted, #6b7280)",
  info: "var(--info, #2563eb)",
  low: "var(--success, #059669)",
  medium: "var(--warning, #d97706)",
  high: "var(--danger, #dc2626)",
  critical: "var(--critical, #7f1d1d)",
};

export function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

export function severityRank(severity: string | undefined | null): number {
  const key = (severity || "none").toLowerCase() as Severity;
  return SEVERITY_RANK[key] ?? 0;
}

export function normalizeSeverity(
  severity: string | undefined | null,
): Severity {
  const key = (severity || "none").toLowerCase();
  return (key in SEVERITY_RANK ? key : "none") as Severity;
}

export function compareSeverity(a: string, b: string): number {
  return severityRank(a) - severityRank(b);
}

export function maxSeverity(
  values: Array<string | undefined | null>,
): Severity {
  let best: Severity = "none";
  for (const value of values) {
    if (severityRank(value) > severityRank(best)) {
      best = normalizeSeverity(value);
    }
  }
  return best;
}

export function severityLabel(severity: string | undefined | null): string {
  const normalized = normalizeSeverity(severity);
  if (normalized === "none") return "None";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export function severityTone(severity: string | undefined | null): string {
  const normalized = normalizeSeverity(severity);
  if (normalized === "critical" || normalized === "high") return "danger";
  if (normalized === "medium") return "warning";
  if (normalized === "low" || normalized === "info") return "info";
  return "neutral";
}

export function formatCount(
  count: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function formatPercent(value: number, digits = 0): string {
  return `${(clamp(value, 0, 1) * 100).toFixed(digits)}%`;
}

export function formatScore(score: number): string {
  return clamp(score, 0, 10).toFixed(1);
}

export function truncate(text: string, max = 120): string {
  if (text.length <= max) return text;
  if (max <= 1) return "…";
  return `${text.slice(0, max - 1)}…`;
}

export function compactWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function splitLines(text: string): string[] {
  if (!text) return [];
  return text.replace(/\r\n?/g, "\n").split("\n");
}

export function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

export function sortFindings(findings: SecretFinding[]): SecretFinding[] {
  return [...findings].sort((a, b) => {
    const severityDiff = severityRank(b.severity) - severityRank(a.severity);
    if (severityDiff !== 0) return severityDiff;
    if (a.start !== b.start) return a.start - b.start;
    return a.name.localeCompare(b.name);
  });
}

export function groupFindingsBySeverity(
  findings: SecretFinding[],
): Record<Severity, SecretFinding[]> {
  const groups: Record<Severity, SecretFinding[]> = {
    none: [],
    info: [],
    low: [],
    medium: [],
    high: [],
    critical: [],
  };
  for (const finding of findings) {
    groups[normalizeSeverity(finding.severity)].push(finding);
  }
  return groups;
}

export function groupFindingsByName(
  findings: SecretFinding[],
): Array<{ name: string; count: number; severity: Severity }> {
  const map = new Map<
    string,
    { name: string; count: number; severity: Severity }
  >();
  for (const finding of findings) {
    const existing = map.get(finding.name);
    if (!existing) {
      map.set(finding.name, {
        name: finding.name,
        count: 1,
        severity: normalizeSeverity(finding.severity),
      });
      continue;
    }
    existing.count += 1;
    if (severityRank(finding.severity) > severityRank(existing.severity)) {
      existing.severity = normalizeSeverity(finding.severity);
    }
  }
  return [...map.values()].sort((a, b) => {
    const severityDiff = severityRank(b.severity) - severityRank(a.severity);
    if (severityDiff !== 0) return severityDiff;
    if (a.count !== b.count) return b.count - a.count;
    return a.name.localeCompare(b.name);
  });
}

export function filterFindings(
  findings: SecretFinding[],
  options: { query?: string; severities?: Severity[]; names?: string[] } = {},
): SecretFinding[] {
  const query = (options.query || "").trim().toLowerCase();
  const severities = options.severities?.length
    ? new Set(options.severities)
    : null;
  const names = options.names?.length ? new Set(options.names) : null;
  return findings.filter((finding) => {
    if (severities && !severities.has(normalizeSeverity(finding.severity)))
      return false;
    if (names && !names.has(finding.name)) return false;
    if (!query) return true;
    return (
      finding.name.toLowerCase().includes(query) ||
      finding.masked.toLowerCase().includes(query) ||
      finding.context.toLowerCase().includes(query) ||
      finding.tags.some((tag) => tag.toLowerCase().includes(query))
    );
  });
}

export function scanSummary(
  result: SecretScanResult | null | undefined,
): string {
  if (!result) return "No scan results";
  if (result.count === 0) return "No secrets detected";
  return `${formatCount(result.count, "finding")} · highest ${severityLabel(result.highest_severity)}`;
}

export function redactionSummaryText(
  summary: RedactionSummary | null | undefined,
): string {
  if (!summary) return "No redactions applied";
  if (summary.total_replacements === 0) return "No sensitive content redacted";
  const rules = summary.applied.length
    ? ` across ${formatCount(summary.applied.length, "rule")}`
    : "";
  return `${formatCount(summary.total_replacements, "replacement")}${rules}`;
}

export function consentProgress(
  summary: ConsentSummary | null | undefined,
): number {
  if (!summary || summary.total === 0) return 0;
  return summary.granted / summary.total;
}

export function privacyControlMap(
  mode: PrivacyMode | null | undefined,
): Record<string, boolean> {
  const map: Record<string, boolean> = {};
  for (const control of mode?.controls || []) {
    map[control.key] = control.enabled;
  }
  return map;
}

export function enabledControls(controls: PrivacyControl[]): PrivacyControl[] {
  return controls.filter((control) => control.enabled);
}

export function disabledControls(controls: PrivacyControl[]): PrivacyControl[] {
  return controls.filter((control) => !control.enabled);
}

export function policyDecisionTone(
  decision: PolicyEvaluation | null | undefined,
): string {
  if (!decision) return "neutral";
  if (decision.decision === "allow") return "success";
  if (decision.decision === "deny") return "danger";
  return "warning";
}

export function auditSeverityCounts(
  report: AuditReport | null | undefined,
): Record<Severity, number> {
  const counts: Record<Severity, number> = {
    none: 0,
    info: 0,
    low: 0,
    medium: 0,
    high: 0,
    critical: 0,
  };
  for (const finding of report?.findings || []) {
    counts[normalizeSeverity(finding.severity)] += 1;
  }
  return counts;
}

export function sortAuditFindings(findings: AuditFinding[]): AuditFinding[] {
  return [...findings].sort((a, b) => {
    const severityDiff = severityRank(b.severity) - severityRank(a.severity);
    if (severityDiff !== 0) return severityDiff;
    if (a.count !== b.count) return b.count - a.count;
    return a.code.localeCompare(b.code);
  });
}

export function timelineMaxCount(
  report: AuditReport | null | undefined,
): number {
  let max = 0;
  for (const bucket of report?.timeline || []) {
    for (const [key, value] of Object.entries(bucket)) {
      if (key === "bucket" || typeof value !== "number") continue;
      if (value > max) max = value;
    }
  }
  return max;
}

export function riskGaugePercent(score: number): number {
  return clamp(score, 0, 10) * 10;
}

export function riskTone(level: string | undefined | null): string {
  const normalized = normalizeSeverity(level);
  if (normalized === "critical" || normalized === "high") return "danger";
  if (normalized === "medium") return "warning";
  if (normalized === "low" || normalized === "info") return "info";
  return "success";
}

export function riskHeadline(
  assessment: RiskAssessment | null | undefined,
): string {
  if (!assessment) return "No risk assessment";
  return `${severityLabel(assessment.score.level)} risk · ${formatScore(assessment.score.score)}/10`;
}

export function topRiskFactors(
  assessment: RiskAssessment | null | undefined,
  limit = 4,
) {
  if (!assessment) return [];
  return [...assessment.factors]
    .sort(
      (a, b) =>
        b.weighted_score - a.weighted_score ||
        severityRank(b.severity) - severityRank(a.severity),
    )
    .slice(0, limit);
}

export function isSafeUrlSafety(result: UrlSafety | null | undefined): boolean {
  return Boolean(result?.safe);
}

export function isSafeCommandSafety(
  result: CommandSafety | null | undefined,
): boolean {
  return Boolean(result?.safe);
}

export function safetyReasonsText(
  reasons: string[] | undefined | null,
): string {
  if (!reasons?.length) return "No issues detected";
  return reasons.map((reason) => reason.replace(/[_:]/g, " ")).join(", ");
}

export function dashboardAlerts(
  dashboard: SecurityDashboard | null | undefined,
): string[] {
  if (!dashboard) return [];
  const alerts: string[] = [];
  if (dashboard.secrets.count > 0) alerts.push(scanSummary(dashboard.secrets));
  if (dashboard.audit.findings.length > 0)
    alerts.push(
      `${formatCount(dashboard.audit.findings.length, "audit finding")}`,
    );
  const unsafeUrls = dashboard.urls.filter((item) => !item.safe).length;
  const unsafeCommands = dashboard.commands.filter((item) => !item.safe).length;
  if (unsafeUrls > 0) alerts.push(`${formatCount(unsafeUrls, "unsafe URL")}`);
  if (unsafeCommands > 0)
    alerts.push(`${formatCount(unsafeCommands, "risky command")}`);
  if (dashboard.scrub?.report?.total_redactions) {
    alerts.push(
      `${formatCount(dashboard.scrub.report.total_redactions, "scrub redaction")}`,
    );
  }
  return alerts;
}

export function dashboardStatus(
  dashboard: SecurityDashboard | null | undefined,
): {
  label: string;
  tone: string;
} {
  if (!dashboard) return { label: "Unknown", tone: "neutral" };
  const level = normalizeSeverity(dashboard.risk.score.level);
  return { label: `${severityLabel(level)} risk`, tone: riskTone(level) };
}

export function mergeConsent(
  current: Record<string, boolean>,
  updates: Record<string, boolean>,
): Record<string, boolean> {
  return { ...current, ...updates };
}

export function redactPreviewLabel(
  summary: RedactionSummary | null | undefined,
): string {
  if (!summary) return "Preview unavailable";
  const count = summary.total_replacements;
  if (count === 0) return "No changes";
  return `${count} change${count === 1 ? "" : "s"}`;
}

export function maskIfNeeded(
  text: string,
  masked: string,
  reveal: boolean,
): string {
  return reveal ? text : masked;
}

export function formatConfidence(confidence: number): string {
  return formatPercent(confidence, 0);
}

export function buildPatternOptions(
  patterns: Array<{ name: string }>,
): Array<{ label: string; value: string }> {
  return patterns.map((pattern) => ({
    label: pattern.name,
    value: pattern.name,
  }));
}

export function calculateScanCoverage(
  textLength: number,
  findings: SecretFinding[],
): number {
  if (textLength <= 0 || findings.length === 0) return 0;
  const covered = findings.reduce(
    (total, finding) => total + Math.max(0, finding.length),
    0,
  );
  return clamp(covered / textLength, 0, 1);
}

export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value))
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(",")}}`;
}
