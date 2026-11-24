/** Typed wrapper around the V3 envelope client for automation routes. */

import { V3Client } from "../../v3/apiClient";
import type {
  DagCompilation,
  DiffEntry,
  DryRunTrace,
  Playbook,
  RecurrenceRule,
  RunRecord,
  TimelineItem,
  ValidationIssue,
  VariableResolution as ServerResolution,
} from "./types";

export interface AutomationClientOptions {
  client?: V3Client;
}

export interface ValidateResult {
  playbook_ref: string;
  ok: boolean;
  issues: ValidationIssue[];
  dag: DagCompilation;
  variables: ServerResolution;
}

export interface CompileResult {
  playbook_ref: string;
  dag: DagCompilation;
}

export interface ConnectResult {
  accepted: boolean;
  issue: ValidationIssue | null;
  playbook: Playbook;
}

export interface DryRunResult {
  trace: DryRunTrace;
  timeline: TimelineItem[];
}

export interface RunResult {
  run: RunRecord;
}

export interface RunsResult {
  runs: RunRecord[];
}

export interface RunGetResult {
  run: RunRecord;
  timeline: TimelineItem[];
}

export interface ReplayResult {
  replay: {
    original_id: string;
    deterministic: boolean;
    trace_digest: string;
    differences: DiffEntry[];
  };
}

export interface RollbackResult {
  rollback: {
    run: RunRecord;
    original_id: string;
    baseline_digest: string;
    result_digest: string;
    equivalent: boolean;
    compensations: number;
    issues: ValidationIssue[];
    ok: boolean;
  };
}

export interface RecurrenceResult {
  rule: RecurrenceRule;
  description: string;
  issues: ValidationIssue[];
  timestamps: number[];
}

export class AutomationClient {
  private readonly client: V3Client;

  constructor(options: AutomationClientOptions = {}) {
    this.client = options.client ?? new V3Client();
  }

  validate(
    playbook: Playbook,
    values: Record<string, unknown>,
  ): Promise<ValidateResult> {
    return this.client.data("automation", "validate", { playbook, values });
  }

  compile(playbook: Playbook): Promise<CompileResult> {
    return this.client.data("automation", "compile", { playbook });
  }

  connect(
    playbook: Playbook,
    source: string,
    target: string,
  ): Promise<ConnectResult> {
    return this.client.data("automation", "connect", {
      playbook,
      source,
      target,
    });
  }

  dryRun(
    playbook: Playbook,
    values: Record<string, unknown>,
  ): Promise<DryRunResult> {
    return this.client.data("automation", "dry_run", { playbook, values });
  }

  run(playbook: Playbook, values: Record<string, unknown>): Promise<RunResult> {
    return this.client.data("automation", "run", { playbook, values });
  }

  runs(playbookRef?: string, limit = 100): Promise<RunsResult> {
    return this.client.data("automation", "runs", {
      playbook_ref: playbookRef ?? "",
      limit,
    });
  }

  runGet(runId: string): Promise<RunGetResult> {
    return this.client.data("automation", "run_get", { run_id: runId });
  }

  replay(
    runId: string,
    values: Record<string, unknown> = {},
  ): Promise<ReplayResult> {
    return this.client.data("automation", "replay", { run_id: runId, values });
  }

  rollback(runId: string): Promise<RollbackResult> {
    return this.client.data("automation", "rollback", { run_id: runId });
  }

  recurrence(
    rule: RecurrenceRule,
    after: number,
    before: number,
    limit = 20,
  ): Promise<RecurrenceResult> {
    return this.client.data("automation", "recurrence", {
      rule,
      after,
      before,
      limit,
    });
  }

  diff(left: string, right: string): Promise<{ differences: DiffEntry[] }> {
    return this.client.data("automation", "diff", { left, right });
  }
}
