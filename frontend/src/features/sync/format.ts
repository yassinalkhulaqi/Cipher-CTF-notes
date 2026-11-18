import type {
  ChangeRecord,
  ConflictRecord,
  DryRunReport,
  MergePreview,
  ProgressReport,
  SyncFormat,
  WizardStep,
} from "./types";

export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 100) return 100;
  return Math.round(value * 100) / 100;
}

export function formatPercent(value: number): string {
  return `${clampPercent(value).toFixed(clampPercent(value) % 1 === 0 ? 0 : 1)}%`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  const digits = unit === 0 || Number.isInteger(rounded) ? 0 : 1;
  return `${rounded.toFixed(digits)} ${units[unit]}`;
}

export function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return Math.max(0, Math.floor(value)).toLocaleString("en-US");
}

export function formatDateTime(value: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function shortChecksum(value: string, size = 12): string {
  const text = value.trim();
  if (!text) return "—";
  if (text.length <= size) return text;
  return `${text.slice(0, Math.max(4, size - 4))}…${text.slice(-4)}`;
}

export function titleForFormat(format: SyncFormat): string {
  switch (format) {
    case "json":
      return "JSON snapshot";
    case "markdown":
      return "Markdown export";
    case "html":
      return "HTML report";
    case "sqlite":
      return "SQLite backup";
    default:
      return format;
  }
}

export function changeTone(action: ChangeRecord["action"]): string {
  switch (action) {
    case "create":
      return "success";
    case "update":
      return "warning";
    case "delete":
      return "danger";
    default:
      return "neutral";
  }
}

export function conflictTone(kind: string): string {
  if (kind === "delete_vs_edit" || kind === "schema") return "danger";
  if (kind === "content" || kind === "duplicate") return "warning";
  return "neutral";
}

export function resolutionLabel(value: string): string {
  switch (value) {
    case "keep_local":
      return "Keep local";
    case "keep_remote":
      return "Keep remote";
    case "merged":
      return "Merge";
    case "skip":
      return "Skip";
    case "unresolved":
      return "Unresolved";
    default:
      return value.replaceAll("_", " ");
  }
}

export function progressLabel(
  report: ProgressReport | null | undefined,
): string {
  if (!report) return "Idle";
  const detail = report.message ? ` — ${report.message}` : "";
  return `${report.stage} ${formatPercent(report.percent)}${detail}`;
}

export function summarizeChanges(
  changes: ChangeRecord[],
): Record<string, number> {
  const summary = {
    total: changes.length,
    create: 0,
    update: 0,
    delete: 0,
    unchanged: 0,
  };
  for (const change of changes) {
    if (change.action in summary) {
      summary[change.action] += 1;
    }
  }
  return summary;
}

export function summarizeConflicts(
  conflicts: ConflictRecord[],
): Record<string, number> {
  const summary = {
    total: conflicts.length,
    unresolved: 0,
    keep_local: 0,
    keep_remote: 0,
    merged: 0,
    skip: 0,
  };
  for (const conflict of conflicts) {
    if (conflict.resolution in summary) {
      summary[conflict.resolution as keyof typeof summary] += 1;
    }
  }
  return summary;
}

export function summarizeMerge(
  merge: MergePreview | Record<string, unknown>,
): string {
  const counts = (merge as { counts?: Record<string, number> }).counts;
  if (counts) {
    return `${formatCount(counts.applied ?? 0)} applied, ${formatCount(counts.skipped ?? 0)} skipped, ${formatCount(counts.conflicts ?? 0)} conflicts`;
  }
  const applied = Array.isArray((merge as MergePreview).applied)
    ? (merge as MergePreview).applied.length
    : 0;
  const skipped = Array.isArray((merge as MergePreview).skipped)
    ? (merge as MergePreview).skipped.length
    : 0;
  const conflicts = Array.isArray((merge as MergePreview).conflicts)
    ? (merge as MergePreview).conflicts.length
    : 0;
  return `${formatCount(applied)} applied, ${formatCount(skipped)} skipped, ${formatCount(conflicts)} conflicts`;
}

export function dryRunHeadline(report: DryRunReport): string {
  if (!report.valid) return `${report.operation} dry run found issues`;
  const changes = Array.isArray(report.changes) ? report.changes.length : 0;
  const conflicts = Array.isArray(report.conflicts)
    ? report.conflicts.length
    : 0;
  if (report.operation === "import") {
    return `${formatCount(changes)} changes, ${formatCount(conflicts)} conflicts`;
  }
  return `${report.operation} ready`;
}

export function wizardPercent(steps: WizardStep[]): number {
  if (!steps.length) return 0;
  const complete = steps.filter((step) => step.status === "complete").length;
  return clampPercent((complete / steps.length) * 100);
}

export function statusBadge(status: string): string {
  if (status === "completed" || status === "complete") return "success";
  if (status === "failed" || status === "error") return "danger";
  if (status === "running" || status === "active") return "warning";
  return "neutral";
}

export function describePath(path: string): string {
  const value = path.trim();
  if (!value) return "No path selected";
  const parts = value.split(/[/\\]/).filter(Boolean);
  if (parts.length <= 2) return value;
  return `…/${parts.slice(-2).join("/")}`;
}

export function safeFilename(value: string): string {
  return (
    value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "sync"
  );
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Sync request failed";
}
