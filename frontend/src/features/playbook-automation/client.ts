/** Typed client for the v4 playbook automation API. */

import { V4ApiError, V4Client } from "../v4-kernel/client";
import type { PageMetaV4 } from "../v4-kernel/types-v4";

export type NodeKindV4 =
  | "setup"
  | "collect"
  | "analyze"
  | "enrich"
  | "report"
  | "notify";

export type RunStatusV4 =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type TraceStatusV4 = "planned" | "succeeded" | "failed" | "skipped";

export interface DagNodeV4 {
  id: string;
  label: string;
  kind: NodeKindV4;
  depends_on: string[];
  params: Record<string, string>;
}

export interface DagEdgeV4 {
  source: string;
  target: string;
  label: string;
}

export interface PlaybookDagV4 {
  id: string;
  name: string;
  description: string;
  nodes: DagNodeV4[];
  edges: DagEdgeV4[];
}

export interface TraceStepV4 {
  node_id: string;
  status: TraceStatusV4;
  detail: string;
  duration_ms: number;
}

export interface DryRunResultV4 {
  dag_id: string;
  status: RunStatusV4;
  trace: TraceStepV4[];
  digest: string;
  waves: number;
}

export interface ValidationReportV4 {
  dag_id: string;
  ok: boolean;
  order: string[];
  layers: string[][];
  depth: Record<string, number>;
  critical_path: string[];
  cycles: string[][];
  missing: string[];
  duplicates: string[];
  issues: Array<{
    code: string;
    message: string;
    path: string;
    severity: string;
  }>;
}

export interface RunRecordV4 {
  id: string;
  playbook_id: string;
  status: RunStatusV4;
  started_at: string;
  finished_at: string;
  trace: TraceStepV4[];
  trigger: string;
}

export interface ScheduleV4 {
  id: string;
  playbook_id: string;
  frequency: "interval" | "daily" | "weekly" | "monthly";
  interval_minutes: number;
  minute: number;
  hour: number;
  day_of_week: number[];
  day_of_month: number;
  next_run: string;
  enabled: boolean;
}

export interface PagedV4<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
}

export interface DescribeResultV4 {
  service: string;
  actions: string[];
  capabilities: string[];
}

export interface StatsResultV4 {
  runs: number;
  schedules: number;
  playbooks: number;
  terminal_runs: number;
}

export interface AutomationEnvelope<T> {
  data: T;
  meta: PageMetaV4;
}

export interface RunFilters {
  playbookId?: string;
  status?: RunStatusV4;
  page?: number;
  pageSize?: number;
}

function queryOf(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

/** Thin, fully typed wrapper around the shared v4 fetch client. */
export class PlaybookAutomationClient {
  constructor(private readonly http: V4Client = new V4Client()) {}

  private read<T>(
    action: string,
    filters: Record<string, string | number | undefined>,
  ) {
    const options = {
      page: typeof filters.page === "number" ? filters.page : undefined,
      pageSize:
        typeof filters.pageSize === "number"
          ? filters.pageSize
          : typeof filters.page_size === "number"
            ? filters.page_size
            : undefined,
    };
    const rest: Record<string, string | number | undefined> = { ...filters };
    delete rest.page;
    delete rest.pageSize;
    delete rest.page_size;
    return this.http.get<T>(`/automation/${action}${queryOf(rest)}`, options);
  }

  describe(): Promise<AutomationEnvelope<DescribeResultV4>> {
    return this.read<DescribeResultV4>("describe", {});
  }

  validate(dag: PlaybookDagV4): Promise<ValidationReportV4> {
    return this.http.post<ValidationReportV4>("/automation/validate", { dag });
  }

  listPlaybooks(
    page = 1,
    pageSize = 50,
  ): Promise<AutomationEnvelope<PagedV4<PlaybookDagV4>>> {
    return this.read<PagedV4<PlaybookDagV4>>("playbooks", {
      page,
      page_size: pageSize,
    });
  }

  dryRun(
    dag: PlaybookDagV4,
    failNodes: string[] = [],
  ): Promise<DryRunResultV4> {
    return this.http.post<DryRunResultV4>("/automation/dry-run", {
      dag,
      fail_nodes: failNodes,
    });
  }

  listRuns(
    filters: RunFilters = {},
  ): Promise<AutomationEnvelope<PagedV4<RunRecordV4>>> {
    return this.read<PagedV4<RunRecordV4>>("runs", {
      playbook_id: filters.playbookId,
      status: filters.status,
      page: filters.page,
      page_size: filters.pageSize,
    });
  }

  getRun(runId: string): Promise<AutomationEnvelope<RunRecordV4>> {
    return this.read<RunRecordV4>("run", { run_id: runId });
  }

  startRun(playbookId: string): Promise<RunRecordV4> {
    return this.http.post<RunRecordV4>("/automation/start", {
      playbook_id: playbookId,
    });
  }

  completeRun(runId: string): Promise<RunRecordV4> {
    return this.http.post<RunRecordV4>("/automation/complete", {
      run_id: runId,
    });
  }

  cancelRun(runId: string): Promise<RunRecordV4> {
    return this.http.post<RunRecordV4>("/automation/cancel", { run_id: runId });
  }

  listSchedules(
    playbookId?: string,
  ): Promise<AutomationEnvelope<PagedV4<ScheduleV4>>> {
    return this.read<PagedV4<ScheduleV4>>("schedules", {
      playbook_id: playbookId,
    });
  }

  planSchedule(schedule: ScheduleV4): Promise<ScheduleV4> {
    return this.http.post<ScheduleV4>("/automation/plan-schedule", {
      schedule,
    });
  }

  dueSchedules(): Promise<AutomationEnvelope<PagedV4<ScheduleV4>>> {
    return this.read<PagedV4<ScheduleV4>>("due", {});
  }

  stats(): Promise<AutomationEnvelope<StatsResultV4>> {
    return this.read<StatsResultV4>("stats", {});
  }
}

export { V4ApiError };

export const playbookAutomationClient = new PlaybookAutomationClient();
