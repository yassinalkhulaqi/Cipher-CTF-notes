import type {
  PreviewSection,
  ReportPreview,
  SeverityName,
  SeveritySummary,
} from "./types";

export const SEVERITY_ORDER: readonly SeverityName[] = [
  "info",
  "low",
  "medium",
  "high",
  "critical",
];

const SEVERITY_LABELS: Record<SeverityName, string> = {
  info: "Info",
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

const SEVERITY_RANKS: Record<SeverityName, number> = {
  info: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

export function isSeverity(value: string): value is SeverityName {
  return SEVERITY_ORDER.some((item) => item === value);
}

export function severityRank(value: string): number {
  return isSeverity(value) ? SEVERITY_RANKS[value] : -1;
}

export function severityLabel(value: string): string {
  return isSeverity(value) ? SEVERITY_LABELS[value] : value;
}

export function severityClass(value: string): string {
  return `severity-${isSeverity(value) ? value : "info"}`;
}

export function riskClass(value: string): string {
  const normalized = value.trim().toLowerCase();
  return SEVERITY_ORDER.some((item) => item === normalized)
    ? `risk-${normalized}`
    : "risk-info";
}

export function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return Math.max(0, Math.floor(value)).toLocaleString("en-US");
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 10 || Number.isInteger(value) ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unit]}`;
}

export function formatConfidence(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const bounded = Math.min(1, Math.max(0, value));
  return `${Math.round(bounded * 100)}%`;
}

export function truncate(text: string, max: number): string {
  if (max <= 0) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}

export function compact(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function summarizeSeverity(summary: SeveritySummary | null): string {
  if (!summary) return "No preview";
  const parts = SEVERITY_ORDER.filter((name) => summary.counts[name] > 0).map(
    (name) => `${summary.counts[name]} ${SEVERITY_LABELS[name].toLowerCase()}`,
  );
  return parts.length ? parts.join(" · ") : "No findings";
}

export function severityBar(summary: SeveritySummary | null): Array<{
  name: SeverityName;
  count: number;
  percent: number;
}> {
  if (!summary) return [];
  return SEVERITY_ORDER.map((name) => ({
    name,
    count: summary.counts[name],
    percent: summary.percentages[name] ?? 0,
  }));
}

export function previewRows(preview: ReportPreview | null): PreviewSection[] {
  if (!preview) return [];
  return preview.sections.slice().sort((left, right) => {
    if (left.level !== right.level) return left.level - right.level;
    return left.title.localeCompare(right.title);
  });
}

export function warningList(preview: ReportPreview | null): string[] {
  return preview ? preview.warnings.slice() : [];
}

export function evidenceLabel(key: string): string {
  const labels: Record<string, string> = {
    findings: "Findings",
    findings_with_evidence: "With evidence",
    evidence: "Evidence items",
    sensitive_evidence: "Sensitive",
    notes: "Notes",
    commands: "Commands",
    artifacts: "Artifacts",
    missing: "Missing",
  };
  return labels[key] ?? key.replaceAll("_", " ");
}

export function manifestLines(manifest: Record<string, unknown>): string[] {
  return Object.entries(manifest)
    .filter(([, value]) => typeof value !== "object" || value === null)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`)
    .sort((left, right) => left.localeCompare(right));
}

export function formatKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, "-")
    .replaceAll(/^-|-$/g, "");
}

export function displayName(value: string): string {
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
