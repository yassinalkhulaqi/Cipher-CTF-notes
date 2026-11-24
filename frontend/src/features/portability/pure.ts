/** Pure helpers for the portability wizard, merge workbench, and receipts. */

import type {
  BundlePlan,
  ChangeAction,
  ConflictView,
  DiffRow,
  DryRunView,
  NoticeView,
  ProgressView,
  ReceiptView,
  ReasonCode,
  Resolution,
  Tone,
  TransferPhase,
  VectorView,
  WizardStep,
} from "./types";

export const WIZARD_LABELS: Array<{ id: WizardStep["id"]; label: string; description: string }> = [
  { id: "source", label: "Source", description: "Choose device and vault scope" },
  { id: "scope", label: "Scope & key", description: "Select records and passphrase policy" },
  { id: "dry-run", label: "Dry run", description: "Preview changes before writing" },
  { id: "conflicts", label: "Conflicts", description: "Decide every explained difference" },
  { id: "transfer", label: "Transfer", description: "Track and resume chunk progress" },
  { id: "receipt", label: "Receipt", description: "Archive verification evidence" },
];

export const REASON_CODES: ReasonCode[] = [
  "field_both_edited",
  "delete_modify",
  "concurrent_add",
  "tag_set_divergence",
  "content_divergence",
  "link_target_missing",
  "vector_regression",
  "schema_mismatch",
  "checksum_mismatch",
  "unknown_field",
];

const REASON_LABELS: Record<ReasonCode, string> = {
  field_both_edited: "Same field edited twice",
  delete_modify: "Delete versus edit",
  concurrent_add: "Concurrent creation",
  tag_set_divergence: "Tag sets diverged",
  content_divergence: "Note body diverged",
  link_target_missing: "Link target missing",
  vector_regression: "History regressed",
  schema_mismatch: "Schema mismatch",
  checksum_mismatch: "Checksum mismatch",
  unknown_field: "Unknown field",
};

const REASON_HELP: Record<ReasonCode, string> = {
  field_both_edited: "Both devices changed the same field. Choose a side or merge it manually.",
  delete_modify: "One device deleted the record while the other edited it.",
  concurrent_add: "Two records share an id but were created independently.",
  tag_set_divergence: "Both devices changed the tag set differently.",
  content_divergence: "Both devices edited the note body text.",
  link_target_missing: "A relationship points to an entity outside the merged set.",
  vector_regression: "An incoming vector is missing counters from the common ancestor.",
  schema_mismatch: "The bundle was written by an incompatible schema version.",
  checksum_mismatch: "A record no longer matches the manifest checksum.",
  unknown_field: "The payload contains a field this client does not recognize.",
};

export const RESOLUTIONS: Resolution[] = [
  "unresolved",
  "keep_local",
  "keep_remote",
  "merge_fields",
  "skip",
];

const RESOLUTION_LABELS: Record<Resolution, string> = {
  unresolved: "Undecided",
  keep_local: "Keep local",
  keep_remote: "Keep incoming",
  merge_fields: "Merge fields",
  skip: "Skip record",
};

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function shortDigest(digest: string, length = 12): string {
  if (!digest) return "—";
  return digest.length <= length ? digest : `${digest.slice(0, length)}…`;
}

export function truncate(text: string, maximum = 80): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length <= maximum ? clean : `${clean.slice(0, maximum - 1)}…`;
}

export function formatTimestamp(timestamp: number): string {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "unknown";
  return new Date(timestamp * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

export function buildWizardSteps(): WizardStep[] {
  return WIZARD_LABELS.map((item, index) => ({
    ...item,
    status: index === 0 ? "active" : "pending",
  }));
}

export function advanceWizard(
  steps: WizardStep[],
  index: number,
  status?: WizardStep["status"],
): WizardStep[] {
  if (index < 0 || index >= steps.length) return steps;
  return steps.map((step, position) => {
    if (position === index) {
      return { ...step, status: status ?? (step.status === "complete" ? "complete" : "active") };
    }
    if (position < index && step.status !== "error") {
      return { ...step, status: "complete" };
    }
    if (position > index && step.status === "active") {
      return { ...step, status: "pending" };
    }
    return step;
  });
}

export function wizardPercent(steps: WizardStep[]): number {
  if (!steps.length) return 0;
  const complete = steps.filter((step) => step.status === "complete").length;
  return clamp(Math.round((100 * complete) / steps.length), 0, 100);
}

export function currentStep(steps: WizardStep[]): WizardStep | null {
  return steps.find((step) => step.status === "active") ?? null;
}

export function defaultPlan(): BundlePlan {
  return {
    label: "",
    deviceId: "local",
    passphrase: "",
    includeDeleted: false,
    includeLinks: true,
    dryRun: true,
    scope: ["note", "finding", "evidence", "report"],
  };
}

export function passphraseScore(passphrase: string): number {
  if (!passphrase) return 0;
  const classes = [
    /[a-z]/.test(passphrase),
    /[A-Z]/.test(passphrase),
    /[0-9]/.test(passphrase),
    /[^A-Za-z0-9]/.test(passphrase),
  ].filter(Boolean).length;
  const lengthBonus = passphrase.length >= 12 ? 1 : 0;
  return clamp(classes - 1 + lengthBonus, 1, 4);
}

export function strengthLabel(score: number): string {
  return ["Empty", "Weak", "Fair", "Strong", "Excellent"][clamp(score, 0, 4)] ?? "Weak";
}

export function strengthTone(score: number): Tone {
  return (["bad", "bad", "warn", "good", "good"] as Tone[])[clamp(score, 0, 4)] ?? "bad";
}

export function validatePlan(plan: BundlePlan): string[] {
  const problems: string[] = [];
  if (!plan.label.trim()) problems.push("Give this bundle a recognizable label.");
  if (!plan.deviceId.trim()) problems.push("Select the authoring device.");
  if (passphraseScore(plan.passphrase) < 2) problems.push("Use a longer passphrase with mixed character types.");
  if (!plan.scope.length) problems.push("Select at least one entity family.");
  return problems;
}

export function reasonLabel(code: ReasonCode | string): string {
  return REASON_LABELS[code as ReasonCode] ?? code.replaceAll("_", " ");
}

export function reasonHelp(code: ReasonCode | string): string {
  return REASON_HELP[code as ReasonCode] ?? "This difference needs a manual decision.";
}

export function reasonTone(code: ReasonCode | string): Tone {
  if (code === "delete_modify" || code === "concurrent_add") return "bad";
  if (code === "schema_mismatch" || code === "checksum_mismatch") return "warn";
  return "info";
}

export function resolutionLabel(resolution: Resolution | string): string {
  return RESOLUTION_LABELS[resolution as Resolution] ?? resolution;
}

export function resolutionTone(resolution: Resolution | string): Tone {
  if (resolution === "unresolved") return "warn";
  if (resolution === "skip") return "neutral";
  return "good";
}

export function vectorRelationLabel(relation: string): string {
  const labels: Record<string, string> = {
    equal: "Identical histories",
    left_ahead: "Local history is ahead",
    right_ahead: "Incoming history is ahead",
    concurrent: "Independent edits on both sides",
  };
  return labels[relation] ?? relation.replaceAll("_", " ");
}

export function vectorTone(relation: string): Tone {
  return relation === "concurrent" ? "warn" : relation === "equal" ? "good" : "info";
}

export function vectorSummary(vector: VectorView | null): string {
  if (!vector) return "No vectors compared yet";
  const devices = Object.keys(vector.merged).length;
  return `${devices} device${devices === 1 ? "" : "s"} · distance ${vector.distance}`;
}

export function renderValue(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (Array.isArray(value)) return value.map(renderValue).join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function diffRows(conflict: ConflictView | null): DiffRow[] {
  if (!conflict) return [];
  return conflict.fields.map((field) => ({ ...field }));
}

export function overlappingFields(conflict: ConflictView | null): string[] {
  return diffRows(conflict)
    .filter((field) => field.overlap)
    .map((field) => field.field);
}

export function filterConflicts(
  conflicts: ConflictView[],
  options: { reason?: string; query?: string; unresolvedOnly?: boolean } = {},
): ConflictView[] {
  const needle = (options.query ?? "").trim().toLowerCase();
  return conflicts.filter((conflict) => {
    if (options.reason && conflict.reason !== options.reason) return false;
    if (options.unresolvedOnly && conflict.resolution !== "unresolved") return false;
    if (!needle) return true;
    return `${conflict.ref} ${conflict.message} ${reasonLabel(conflict.reason)}`
      .toLowerCase()
      .includes(needle);
  });
}

export function groupConflicts(conflicts: ConflictView[]): Array<[ReasonCode, ConflictView[]]> {
  const groups = new Map<ReasonCode, ConflictView[]>();
  for (const conflict of conflicts) {
    const list = groups.get(conflict.reason) ?? [];
    list.push(conflict);
    groups.set(conflict.reason, list);
  }
  return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
}

export function conflictCounts(conflicts: ConflictView[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const conflict of conflicts) {
    counts[conflict.reason] = (counts[conflict.reason] ?? 0) + 1;
  }
  return counts;
}

export function unresolvedCount(conflicts: ConflictView[]): number {
  return conflicts.filter((conflict) => conflict.resolution === "unresolved").length;
}

export function suggestResolution(conflict: ConflictView, strategy: string): Resolution {
  if (strategy === "keep_local") return "keep_local";
  if (strategy === "keep_remote") return "keep_remote";
  if (strategy === "skip") return "skip";
  if (strategy === "merge_fields" && conflict.fields.length > 0) return "merge_fields";
  return conflict.suggestion === "unresolved" ? "unresolved" : conflict.suggestion;
}

export function applyResolution(
  conflicts: ConflictView[],
  ref: string,
  resolution: Resolution,
): ConflictView[] {
  return conflicts.map((conflict) =>
    conflict.ref === ref ? { ...conflict, resolution } : conflict,
  );
}

export function stableSortConflicts(conflicts: ConflictView[]): ConflictView[] {
  return [...conflicts].sort(
    (a, b) =>
      a.ref.localeCompare(b.ref) ||
      a.reason.localeCompare(b.reason) ||
      a.severity.localeCompare(b.severity),
  );
}

export function actionTone(action: ChangeAction | string): Tone {
  if (action === "create") return "good";
  if (action === "delete") return "bad";
  if (action === "update") return "info";
  return "neutral";
}

export function summarizeDryRun(report: DryRunView | null): string {
  if (!report) return "Run a dry preview to inspect the incoming bundle.";
  const changeCount = report.changes.length;
  const conflictCount = report.conflicts.length;
  if (!report.valid) return `${changeCount} changes inspected · ${conflictCount} conflicts to resolve`;
  return `${report.headline} · ${changeCount} changes inspected`;
}

export function changesByAction(report: DryRunView | null): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const change of report?.changes ?? []) {
    counts[change.action] = (counts[change.action] ?? 0) + 1;
  }
  return counts;
}

export function progressPercent(received: number, total: number): number {
  if (total <= 0) return 100;
  return clamp(Math.round((100 * received) / total), 0, 100);
}

export function progressLabel(progress: ProgressView | null): string {
  if (!progress) return "No transfer in progress";
  if (progress.phase === "complete") return "Transfer complete and verified";
  if (progress.phase === "cancelled") return "Transfer cancelled";
  if (progress.phase === "failed") return "Transfer failed — resume to retry";
  if (progress.phase === "paused") return `Paused at ${progress.percent}%`;
  return `Transferring · ${progress.percent}%`;
}

export function statusTone(phase: TransferPhase | string): Tone {
  if (phase === "complete") return "good";
  if (phase === "cancelled" || phase === "failed") return "bad";
  if (phase === "paused") return "warn";
  return "info";
}

export function canCancel(progress: ProgressView | null): boolean {
  return (
    progress !== null &&
    (progress.phase === "active" || progress.phase === "preparing" || progress.phase === "paused")
  );
}

export function canResume(progress: ProgressView | null): boolean {
  return (
    progress !== null &&
    (progress.phase === "paused" || progress.phase === "failed" || progress.phase === "active")
  );
}

export function failedChecks(receipt: ReceiptView | null): CheckViewLike[] {
  return (receipt?.checks ?? []).filter((check) => !check.passed);
}

interface CheckViewLike {
  name: string;
  passed: boolean;
  detail: string;
  code: string;
}

export function receiptVerdict(receipt: ReceiptView | null): string {
  if (!receipt) return "Not verified yet";
  if (!receipt.ok) return `Verification failed: ${failedChecks(receipt).length} check(s)`;
  return `Verified on ${formatTimestamp(receipt.verifiedAt)}`;
}

export function noticeForError(message: string): NoticeView {
  return { tone: "bad", title: "Portability operation failed", message };
}

export function noticeForSuccess(title: string, message: string): NoticeView {
  return { tone: "good", title, message };
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Unexpected portability error";
}
