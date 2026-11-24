/** Wire and view types for the V3 vault portability feature. */

export type WizardStatus = "pending" | "active" | "complete" | "error";
export type WizardStepId =
  | "source"
  | "scope"
  | "dry-run"
  | "conflicts"
  | "transfer"
  | "receipt";

export type Resolution =
  | "unresolved"
  | "keep_local"
  | "keep_remote"
  | "merge_fields"
  | "skip";

export type ReasonCode =
  | "field_both_edited"
  | "delete_modify"
  | "concurrent_add"
  | "tag_set_divergence"
  | "content_divergence"
  | "link_target_missing"
  | "vector_regression"
  | "schema_mismatch"
  | "checksum_mismatch"
  | "unknown_field";

export type ChangeAction = "create" | "update" | "delete" | "unchanged";
export type TransferPhase =
  | "idle"
  | "preparing"
  | "active"
  | "paused"
  | "complete"
  | "cancelled"
  | "failed";
export type Tone = "neutral" | "good" | "warn" | "bad" | "info";

export interface WizardStep {
  id: WizardStepId;
  label: string;
  description: string;
  status: WizardStatus;
}

export interface BundlePlan {
  label: string;
  deviceId: string;
  passphrase: string;
  includeDeleted: boolean;
  includeLinks: boolean;
  dryRun: boolean;
  scope: string[];
}

export interface VectorView {
  local: Record<string, number>;
  remote: Record<string, number>;
  relation: string;
  relationLabel: string;
  merged: Record<string, number>;
  distance: number;
  concurrent: boolean;
}

export interface DiffRow {
  field: string;
  base: unknown;
  local: unknown;
  remote: unknown;
  localChanged: boolean;
  remoteChanged: boolean;
  overlap: boolean;
}

export interface ConflictView {
  ref: string;
  family: string;
  reason: ReasonCode;
  reasonDescription: string;
  severity: string;
  message: string;
  fields: DiffRow[];
  suggestion: Resolution;
  resolution: Resolution;
  detail: string;
}

export interface ChangeView {
  ref: string;
  action: ChangeAction;
  family: string;
  title: string;
  fields: string[];
}

export interface DryRunView {
  operation: string;
  valid: boolean;
  headline: string;
  changes: ChangeView[];
  conflicts: ConflictView[];
  warnings: string[];
  counts: Record<string, number>;
}

export interface ProgressView {
  transferId: string;
  bundleId: string;
  phase: TransferPhase;
  percent: number;
  receivedChunks: number;
  totalChunks: number;
  missingChunks: number[];
  canCancel: boolean;
  canResume: boolean;
}

export interface CheckView {
  name: string;
  passed: boolean;
  detail: string;
  code: string;
}

export interface ReceiptView {
  receiptId: string;
  bundleId: string;
  device: string;
  verifiedAt: number;
  status: string;
  ok: boolean;
  digest: string;
  checks: CheckView[];
  rendered?: string;
}

export interface NoticeView {
  tone: Tone;
  title: string;
  message: string;
}

export interface PortabilityState {
  plan: BundlePlan;
  wizard: WizardStep[];
  stepIndex: number;
  dryRun: DryRunView | null;
  conflicts: ConflictView[];
  vector: VectorView | null;
  progress: ProgressView | null;
  receipt: ReceiptView | null;
  audit: Array<{ sequence: number; kind: string }>;
  busy: boolean;
  notice: NoticeView | null;
}

export type PortabilityAction =
  | { type: "plan"; value: Partial<BundlePlan> }
  | { type: "step"; index: number; status?: WizardStatus }
  | { type: "dry-run"; value: DryRunView | null }
  | { type: "conflicts"; value: ConflictView[] }
  | { type: "resolve"; ref: string; resolution: Resolution }
  | { type: "vector"; value: VectorView | null }
  | { type: "progress"; value: ProgressView | null }
  | { type: "receipt"; value: ReceiptView | null }
  | { type: "audit"; value: Array<{ sequence: number; kind: string }> }
  | { type: "busy"; value: boolean }
  | { type: "notice"; value: NoticeView | null }
  | { type: "reset" };
