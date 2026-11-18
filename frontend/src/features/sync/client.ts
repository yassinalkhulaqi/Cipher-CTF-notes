import { V2Client } from "../../lib/apiClient";
import type {
  BackupResult,
  ChecksumReport,
  ConflictSession,
  DryRunReport,
  ExportResult,
  ImportResult,
  MergePreview,
  PortabilityProfile,
  RestoreResult,
  SnapshotPayload,
  SyncHealth,
  SyncSelection,
  VectorComparison,
} from "./types";

export interface SyncRequestOptions {
  idempotencyKey?: string;
  requestId?: string;
  signal?: AbortSignal;
}

export function compact<T extends Record<string, unknown>>(value: T): T {
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (item === undefined || item === null || item === "") continue;
    result[key] = item;
  }
  return result as T;
}

export function backupRequest(
  selection: SyncSelection,
): Record<string, unknown> {
  return compact({
    destination: selection.destinationPath,
    format: selection.format === "json" ? "json" : "sqlite",
    include_deleted: selection.includeDeleted,
    include_settings: selection.includeSettings,
    include_manifest: true,
    include_snippets: true,
    include_history: false,
    dry_run: selection.dryRun,
  });
}

export function restoreRequest(
  selection: SyncSelection,
): Record<string, unknown> {
  return compact({
    source: selection.sourcePath,
    mode: "replace",
    verify_checksums: selection.verifyChecksums,
    dry_run: selection.dryRun,
    allow_incompatible: false,
  });
}

export function exportRequest(
  selection: SyncSelection,
): Record<string, unknown> {
  return compact({
    destination: selection.destinationPath,
    format: selection.format === "sqlite" ? "json" : selection.format,
    include_deleted: selection.includeDeleted,
    include_settings: selection.includeSettings,
    dry_run: selection.dryRun,
  });
}

export function importRequest(
  selection: SyncSelection,
): Record<string, unknown> {
  return compact({
    source: selection.sourcePath,
    format: selection.format === "markdown" ? "markdown" : "json",
    strategy: selection.strategy,
    verify_checksums: selection.verifyChecksums,
    dry_run: selection.dryRun,
  });
}

export class SyncClient {
  constructor(private readonly client: V2Client) {}

  health(options: SyncRequestOptions = {}): Promise<SyncHealth> {
    return this.client.call<SyncHealth>("sync.health", {}, options);
  }

  snapshot(
    includeDeleted = false,
    options: SyncRequestOptions = {},
  ): Promise<SnapshotPayload> {
    return this.client.call<SnapshotPayload>(
      "sync.snapshot",
      { include_deleted: includeDeleted },
      options,
    );
  }

  backup(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<BackupResult> {
    return this.client.call<BackupResult>(
      "sync.backup.create",
      backupRequest(selection),
      options,
    );
  }

  backupPlan(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.backup.plan",
      backupRequest(selection),
      options,
    );
  }

  inspectBackup(
    path: string,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.backup.inspect",
      { path },
      options,
    );
  }

  restore(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<RestoreResult> {
    return this.client.call<RestoreResult>(
      "sync.restore.apply",
      restoreRequest(selection),
      options,
    );
  }

  restorePlan(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.restore.plan",
      restoreRequest(selection),
      options,
    );
  }

  exportData(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<ExportResult> {
    return this.client.call<ExportResult>(
      "sync.export.run",
      exportRequest(selection),
      options,
    );
  }

  exportPlan(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.export.plan",
      exportRequest(selection),
      options,
    );
  }

  importData(
    selection: SyncSelection,
    resolutions: Record<string, string> = {},
    options: SyncRequestOptions = {},
  ): Promise<ImportResult> {
    return this.client.call<ImportResult>(
      "sync.import.run",
      { ...importRequest(selection), resolutions },
      options,
    );
  }

  importPlan(
    selection: SyncSelection,
    options: SyncRequestOptions = {},
  ): Promise<ImportResult> {
    return this.client.call<ImportResult>(
      "sync.import.plan",
      importRequest(selection),
      options,
    );
  }

  dryRun(
    operation: string,
    payload: Record<string, unknown>,
    options: SyncRequestOptions = {},
  ): Promise<DryRunReport> {
    return this.client.call<DryRunReport>(
      "sync.dry_run",
      { operation, payload },
      options,
    );
  }

  detectConflicts(
    payload: Record<string, unknown>,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.conflicts.detect",
      payload,
      options,
    );
  }

  mergePreview(
    payload: Record<string, unknown>,
    options: SyncRequestOptions = {},
  ): Promise<MergePreview> {
    return this.client.call<MergePreview>(
      "sync.merge.preview",
      payload,
      options,
    );
  }

  createConflictSession(
    payload: Record<string, unknown>,
    options: SyncRequestOptions = {},
  ): Promise<ConflictSession> {
    return this.client.call<ConflictSession>(
      "sync.conflicts.session.create",
      payload,
      options,
    );
  }

  resolveConflictSession(
    sessionId: string,
    resolutions: Record<string, string>,
    options: SyncRequestOptions = {},
  ): Promise<ConflictSession> {
    return this.client.call<ConflictSession>(
      "sync.conflicts.session.resolve",
      { session_id: sessionId, resolutions },
      options,
    );
  }

  verifyChecksums(
    payload: Record<string, unknown>,
    options: SyncRequestOptions = {},
  ): Promise<ChecksumReport> {
    return this.client.call<ChecksumReport>(
      "sync.checksums.verify",
      payload,
      options,
    );
  }

  compareVectors(
    local: Record<string, number>,
    remote: Record<string, number>,
    options: SyncRequestOptions = {},
  ): Promise<VectorComparison> {
    return this.client.call<VectorComparison>(
      "sync.vectors.compare",
      { local, remote },
      options,
    );
  }

  migrationCheck(
    manifest: Record<string, unknown>,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.migration.check",
      { manifest },
      options,
    );
  }

  portabilityProfiles(options: SyncRequestOptions = {}): Promise<{
    profiles: PortabilityProfile[];
    matrix: Record<string, unknown>;
  }> {
    return this.client.call("sync.portability.profiles", {}, options);
  }

  progressReport(
    steps: Array<Record<string, unknown>>,
    options: SyncRequestOptions = {},
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      "sync.progress.report",
      { steps },
      options,
    );
  }
}

export function createSyncClient(
  fetcher?: typeof globalThis.fetch,
): SyncClient {
  return new SyncClient(new V2Client({ fetch: fetcher }));
}
