export type SyncFormat = "json" | "markdown" | "html" | "sqlite";
export type MergeStrategy = "skip" | "prefer_local" | "prefer_remote" | "merge";
export type ConflictResolution =
  | "unresolved"
  | "keep_local"
  | "keep_remote"
  | "merged"
  | "skip";
export type OperationKind =
  | "backup"
  | "restore"
  | "export"
  | "import"
  | "dry_run"
  | "migration";

export interface ProgressReport {
  operation: string;
  stage: string;
  current: number;
  total: number;
  message: string;
  percent: number;
  done: boolean;
}

export interface SyncHealth {
  ok: boolean;
  namespace: string;
  records: number;
  formats: SyncFormat[];
  strategies: MergeStrategy[];
  vault: string;
  schema_version: number;
  portability?: Record<string, unknown>;
  state?: Record<string, unknown>;
}

export interface SnapshotManifest {
  manifest_version: string;
  created_at: string;
  app_version: string;
  schema_version: number;
  source: string;
  format: string;
  record_count: number;
  files: Record<string, string>;
  record_checksums: Record<string, string>;
  metadata: Record<string, unknown>;
  digest: string;
}

export interface SnapshotRecord {
  id: number;
  parent_id: number | null;
  title: string;
  kind: string;
  content: string;
  tags: string;
  target: string;
  status: string;
  difficulty: string;
  flag: string;
  pinned: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  path: string;
  checksum: string;
}

export interface SnapshotPayload {
  manifest: SnapshotManifest;
  records: SnapshotRecord[];
}

export interface BackupPlan {
  destination: string;
  include_settings: boolean;
  include_deleted: boolean;
  include_snippets: boolean;
  include_manifest: boolean;
  include_history: boolean;
  format: "sqlite" | "json";
  dry_run: boolean;
  label: string;
}

export interface BackupResult {
  plan: BackupPlan;
  path: string;
  manifest: SnapshotManifest | Record<string, unknown>;
  checksum: string;
  bytes_written: number;
  dry_run: boolean;
  progress: ProgressReport[];
  operation_id?: string;
}

export interface RestorePlan {
  source: string;
  mode: "replace" | "inspect";
  verify_checksums: boolean;
  dry_run: boolean;
  allow_incompatible: boolean;
}

export interface RestoreResult {
  plan: RestorePlan;
  restored_path: string;
  manifest: Record<string, unknown>;
  verified: boolean;
  dry_run: boolean;
  warnings: string[];
  progress: ProgressReport[];
  operation_id?: string;
}

export interface ExportPlan {
  destination: string;
  format: "json" | "markdown" | "html";
  include_deleted: boolean;
  include_settings: boolean;
  dry_run: boolean;
  label: string;
}

export interface ExportResult {
  plan: ExportPlan;
  dry_run: boolean;
  path: string;
  manifest_path?: string;
  manifest: Record<string, unknown>;
  records: number;
  progress?: ProgressReport[];
  operation_id?: string;
}

export interface ImportPlan {
  source: string;
  format: "auto" | "json" | "markdown";
  strategy: MergeStrategy;
  verify_checksums: boolean;
  dry_run: boolean;
  parent_id: number | null;
}

export interface ChangeRecord {
  key: string;
  action: "create" | "update" | "delete" | "unchanged";
  entity_type: string;
  title: string;
  path: string;
  checksum: string;
  updated_at: string;
  local?: Record<string, unknown> | null;
  remote?: Record<string, unknown> | null;
}

export interface ConflictRecord {
  key: string;
  kind: string;
  path: string;
  title: string;
  local_checksum: string;
  remote_checksum: string;
  local_updated_at: string;
  remote_updated_at: string;
  resolution: ConflictResolution;
  details: Record<string, unknown>;
  suggested: string;
}

export interface DryRunReport {
  operation: string;
  valid: boolean;
  summary: Record<string, unknown>;
  changes?: ChangeRecord[];
  conflicts?: ConflictRecord[];
  warnings: string[];
  progress?: ProgressReport | null;
  report_summary?: Record<string, unknown>;
}

export interface MergePreview {
  strategy: MergeStrategy;
  applied: ChangeRecord[];
  skipped: ChangeRecord[];
  conflicts: ConflictRecord[];
  dry_run: boolean;
  counts?: Record<string, number>;
}

export interface ImportResult {
  plan: ImportPlan;
  dry_run: boolean;
  local_records: number;
  remote_records: number;
  merge: MergePreview | Record<string, unknown>;
  progress?: ProgressReport[];
  operation_id?: string;
}

export interface ChecksumReport {
  algorithm?: string;
  ok?: boolean;
  expected?: Record<string, string>;
  actual?: Record<string, string>;
  missing?: string[];
  extra?: string[];
  mismatched?: Record<string, { expected: string; actual: string }>;
  counts?: Record<string, number>;
  path?: string;
  checksum?: string;
  files?: Record<string, string>;
  count?: number;
}

export interface ConflictSession {
  session_id: string;
  operation: string;
  created_at: string;
  resolved: boolean;
  conflicts: ConflictRecord[];
  metadata: Record<string, unknown>;
  summary: {
    total: number;
    unresolved: number;
  };
  detection?: Record<string, unknown>;
}

export interface PortabilityProfile {
  name: string;
  format: SyncFormat;
  include_deleted: boolean;
  include_settings: boolean;
  include_history: boolean;
  verify_checksums: boolean;
  strategy: MergeStrategy;
  description: string;
}

export interface WizardStep {
  id: string;
  title: string;
  description: string;
  status: "pending" | "active" | "complete" | "error";
}

export interface SyncNotice {
  tone: "neutral" | "success" | "warning" | "danger";
  title: string;
  message: string;
}

export interface OperationLogEntry {
  id: string;
  at: string;
  operation: string;
  status: "planned" | "running" | "completed" | "failed";
  summary: string;
}

export interface SyncSelection {
  sourcePath: string;
  destinationPath: string;
  format: SyncFormat;
  strategy: MergeStrategy;
  dryRun: boolean;
  verifyChecksums: boolean;
  includeSettings: boolean;
  includeDeleted: boolean;
}

export interface VectorComparison {
  local: Record<string, number>;
  remote: Record<string, number>;
  relation: "equal" | "local" | "remote" | "concurrent";
  merged: Record<string, number>;
}
