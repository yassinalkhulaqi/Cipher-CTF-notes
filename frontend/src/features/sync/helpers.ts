import type {
  ChangeRecord,
  ConflictRecord,
  ConflictSession,
  DryRunReport,
  ImportPlan,
  MergeStrategy,
  PortabilityProfile,
  ProgressReport,
  SyncFormat,
  SyncSelection,
  WizardStep,
} from "./types";

export const SYNC_FORMATS: SyncFormat[] = [
  "json",
  "markdown",
  "html",
  "sqlite",
];
export const MERGE_STRATEGIES: MergeStrategy[] = [
  "merge",
  "prefer_local",
  "prefer_remote",
  "skip",
];

export function defaultSelection(): SyncSelection {
  return {
    sourcePath: "",
    destinationPath: "",
    format: "json",
    strategy: "merge",
    dryRun: true,
    verifyChecksums: true,
    includeSettings: false,
    includeDeleted: false,
  };
}

export function normalizePath(value: string): string {
  return value.trim().replace(/\\/g, "/");
}

export function inferFormat(path: string): SyncFormat {
  const value = normalizePath(path).toLowerCase();
  if (value.endsWith(".db") || value.endsWith(".sqlite")) return "sqlite";
  if (value.endsWith(".html") || value.endsWith(".htm")) return "html";
  if (
    value.endsWith(".md") ||
    value.endsWith(".markdown") ||
    value.endsWith("/")
  ) {
    return "markdown";
  }
  return "json";
}

export function canUseFormatForImport(format: SyncFormat): boolean {
  return format === "json" || format === "markdown";
}

export function canUseFormatForExport(format: SyncFormat): boolean {
  return format === "json" || format === "markdown" || format === "html";
}

export function canUseFormatForBackup(format: SyncFormat): boolean {
  return format === "sqlite" || format === "json";
}

export function validateBackupSelection(selection: SyncSelection): string[] {
  const errors: string[] = [];
  if (!selection.destinationPath.trim())
    errors.push("Destination path is required");
  if (!canUseFormatForBackup(selection.format)) {
    errors.push("Backups support sqlite or json formats");
  }
  return errors;
}

export function validateRestoreSelection(selection: SyncSelection): string[] {
  const errors: string[] = [];
  if (!selection.sourcePath.trim()) errors.push("Source path is required");
  return errors;
}

export function validateExportSelection(selection: SyncSelection): string[] {
  const errors: string[] = [];
  if (!selection.destinationPath.trim())
    errors.push("Destination path is required");
  if (!canUseFormatForExport(selection.format)) {
    errors.push("Exports support json, markdown, or html formats");
  }
  return errors;
}

export function validateImportSelection(selection: SyncSelection): string[] {
  const errors: string[] = [];
  if (!selection.sourcePath.trim()) errors.push("Source path is required");
  if (!canUseFormatForImport(selection.format)) {
    errors.push("Imports support json or markdown formats");
  }
  if (!MERGE_STRATEGIES.includes(selection.strategy)) {
    errors.push("Merge strategy is invalid");
  }
  return errors;
}

export function buildWizardSteps(_kind: string): WizardStep[] {
  const common = [
    { id: "select", title: "Select", description: "Choose paths and options" },
    { id: "preview", title: "Preview", description: "Run a dry-run check" },
    {
      id: "review",
      title: "Review",
      description: "Inspect changes and conflicts",
    },
    { id: "run", title: "Run", description: "Apply the operation" },
  ];
  return common.map((step, index) => ({
    ...step,
    status: index === 0 ? "active" : "pending",
  }));
}

export function advanceWizard(
  steps: WizardStep[],
  index: number,
  status: WizardStep["status"] = "complete",
): WizardStep[] {
  return steps.map((step, current) => {
    if (current < index) return { ...step, status: "complete" };
    if (current === index) return { ...step, status };
    if (current === index + 1 && status === "complete") {
      return { ...step, status: "active" };
    }
    return { ...step, status: "pending" };
  });
}

export function activeWizardIndex(steps: WizardStep[]): number {
  const index = steps.findIndex((step) => step.status === "active");
  return index >= 0 ? index : 0;
}

export function filterActionableChanges(
  changes: ChangeRecord[],
): ChangeRecord[] {
  return changes.filter((change) => change.action !== "unchanged");
}

export function groupChangesByAction(
  changes: ChangeRecord[],
): Record<string, ChangeRecord[]> {
  const groups: Record<string, ChangeRecord[]> = {
    create: [],
    update: [],
    delete: [],
    unchanged: [],
  };
  for (const change of changes) {
    const bucket = groups[change.action] ?? [];
    bucket.push(change);
    groups[change.action] = bucket;
  }
  return groups;
}

export function unresolvedConflicts(
  conflicts: ConflictRecord[],
): ConflictRecord[] {
  return conflicts.filter((conflict) => conflict.resolution === "unresolved");
}

export function applyConflictResolution(
  conflicts: ConflictRecord[],
  key: string,
  resolution: ConflictRecord["resolution"],
): ConflictRecord[] {
  return conflicts.map((conflict) =>
    conflict.key === key ? { ...conflict, resolution } : conflict,
  );
}

export function applyBulkResolution(
  conflicts: ConflictRecord[],
  resolution: ConflictRecord["resolution"],
): ConflictRecord[] {
  return conflicts.map((conflict) => ({ ...conflict, resolution }));
}

export function resolutionMap(
  conflicts: ConflictRecord[],
): Record<string, string> {
  const result: Record<string, string> = {};
  for (const conflict of conflicts) {
    if (conflict.resolution !== "unresolved") {
      result[conflict.key] = conflict.resolution;
    }
  }
  return result;
}

export function mergeStrategyHelp(strategy: MergeStrategy): string {
  switch (strategy) {
    case "merge":
      return "Combine non-conflicting changes and require decisions for conflicts.";
    case "prefer_local":
      return "Keep local content when changes overlap.";
    case "prefer_remote":
      return "Apply remote content when changes overlap.";
    case "skip":
      return "Skip conflicting or overlapping changes and keep existing data.";
    default:
      return "";
  }
}

export function profileToSelection(
  profile: PortabilityProfile,
  base: SyncSelection = defaultSelection(),
): SyncSelection {
  return {
    ...base,
    format: profile.format,
    strategy: profile.strategy,
    verifyChecksums: profile.verify_checksums,
    includeSettings: profile.include_settings,
    includeDeleted: profile.include_deleted,
  };
}

export function importPlanFromSelection(selection: SyncSelection): ImportPlan {
  const format = selection.format === "markdown" ? "markdown" : "json";
  return {
    source: selection.sourcePath.trim(),
    format,
    strategy: selection.strategy,
    verify_checksums: selection.verifyChecksums,
    dry_run: selection.dryRun,
    parent_id: null,
  };
}

export function latestProgress(
  reports: ProgressReport[] | undefined,
): ProgressReport | null {
  if (!reports || reports.length === 0) return null;
  return reports[reports.length - 1] ?? null;
}

export function aggregateProgress(reports: ProgressReport[]): number {
  if (!reports.length) return 0;
  const done = reports.filter((item) => item.done).length;
  return Math.round((done / reports.length) * 100);
}

export function dryRunChanges(report: DryRunReport | null): ChangeRecord[] {
  if (!report) return [];
  if (Array.isArray(report.changes)) return report.changes;
  const merge = report.summary?.merge as
    | { applied?: ChangeRecord[]; skipped?: ChangeRecord[] }
    | undefined;
  if (merge) {
    return [...(merge.applied ?? []), ...(merge.skipped ?? [])];
  }
  return [];
}

export function dryRunConflicts(report: DryRunReport | null): ConflictRecord[] {
  if (!report) return [];
  if (Array.isArray(report.conflicts)) return report.conflicts;
  const merge = report.summary?.merge as
    | { conflicts?: ConflictRecord[] }
    | undefined;
  return merge?.conflicts ?? [];
}

export function sessionIsComplete(session: ConflictSession | null): boolean {
  if (!session) return false;
  return (
    session.resolved ||
    session.conflicts.every((item) => item.resolution !== "unresolved")
  );
}

export function recommendResolution(
  conflict: ConflictRecord,
): ConflictRecord["resolution"] {
  if (
    conflict.suggested === "keep_local" ||
    conflict.suggested === "keep_remote" ||
    conflict.suggested === "merged" ||
    conflict.suggested === "skip"
  ) {
    return conflict.suggested;
  }
  return conflict.remote_updated_at >= conflict.local_updated_at
    ? "keep_remote"
    : "keep_local";
}

export function stableSortByPath<
  T extends { path?: string; title?: string; key?: string },
>(items: T[]): T[] {
  return [...items].sort((left, right) => {
    const a = (left.path || left.title || left.key || "").toLowerCase();
    const b = (right.path || right.title || right.key || "").toLowerCase();
    return a.localeCompare(b);
  });
}

export function filterByQuery<
  T extends { path?: string; title?: string; key?: string },
>(items: T[], query: string): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) => {
    const haystack =
      `${item.path ?? ""} ${item.title ?? ""} ${item.key ?? ""}`.toLowerCase();
    return haystack.includes(needle);
  });
}

export function createOperationLogId(prefix = "sync"): string {
  const stamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${stamp}-${random}`;
}
