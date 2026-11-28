/** Reducer, selectors and deterministic DAG layout for the v4 automation UI. */

import type {
  DagNodeV4,
  PlaybookDagV4,
  RunRecordV4,
  RunStatusV4,
  ScheduleV4,
  TraceStepV4,
  ValidationReportV4,
} from "./client";

export interface DagCell {
  id: string;
  label: string;
  kind: string;
  column: number;
  row: number;
  depth: number;
}

export interface EdgeSegment {
  id: string;
  source: string;
  target: string;
  column: number;
  row: number;
  span: number;
  label: string;
}

export interface TraceSummary {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  durationMs: number;
  maxDurationMs: number;
}

export interface PlaybookAutomationState {
  dag: PlaybookDagV4;
  selectedNodeId: string;
  validation: ValidationReportV4 | null;
  trace: TraceStepV4[];
  runs: RunRecordV4[];
  schedules: ScheduleV4[];
  statusFilter: string;
  page: number;
  busy: boolean;
  error: string;
}

export type PlaybookAutomationAction =
  | { type: "set-dag"; dag: PlaybookDagV4 }
  | { type: "select-node"; id: string }
  | { type: "set-validation"; report: ValidationReportV4 }
  | { type: "set-trace"; trace: TraceStepV4[] }
  | { type: "set-runs"; runs: RunRecordV4[] }
  | { type: "set-schedules"; schedules: ScheduleV4[] }
  | { type: "set-filter"; status: string }
  | { type: "set-page"; page: number }
  | { type: "set-busy"; busy: boolean }
  | { type: "set-error"; error: string }
  | { type: "add-node"; node: DagNodeV4 }
  | { type: "remove-node"; id: string }
  | { type: "toggle-dependency"; from: string; to: string }
  | { type: "update-schedule"; schedule: ScheduleV4 }
  | { type: "reset" };

export function topologicalOrder(dag: PlaybookDagV4): string[] {
  const ids = dag.nodes.map((node) => node.id);
  const known = new Set(ids);
  const incoming = new Map<string, string[]>();
  for (const id of ids) incoming.set(id, []);
  for (const node of dag.nodes) {
    for (const dependency of node.depends_on) {
      if (known.has(dependency) && dependency !== node.id) {
        incoming.get(node.id)?.push(dependency);
      }
    }
  }
  for (const edge of dag.edges) {
    if (
      known.has(edge.source) &&
      known.has(edge.target) &&
      edge.source !== edge.target
    ) {
      incoming.get(edge.target)?.push(edge.source);
    }
  }
  const remaining = new Map<string, number>();
  for (const [id, deps] of incoming) remaining.set(id, new Set(deps).size);
  const ready = ids.filter((id) => remaining.get(id) === 0).sort();
  const order: string[] = [];
  while (ready.length) {
    const id = ready.shift() as string;
    order.push(id);
    for (const node of dag.nodes) {
      if ((incoming.get(node.id) ?? []).includes(id)) {
        const left = (remaining.get(node.id) ?? 1) - 1;
        remaining.set(node.id, left);
        if (left === 0) {
          ready.push(node.id);
          ready.sort();
        }
      }
    }
  }
  return order;
}

export function layoutDag(dag: PlaybookDagV4): DagCell[] {
  const order = topologicalOrder(dag);
  const depth: Record<string, number> = {};
  const depths = new Map<string, number>();
  for (const id of order) {
    const deps =
      dag.nodes
        .find((node) => node.id === id)
        ?.depends_on.filter((dep) => depths.has(dep)) ?? [];
    const value = deps.length
      ? Math.max(...deps.map((dep) => depths.get(dep) ?? 0)) + 1
      : 0;
    depths.set(id, value);
    depth[id] = value;
  }
  const rows: Record<number, number> = {};
  return dag.nodes.map((node) => {
    const column = depth[node.id] ?? 0;
    const row = rows[column] ?? 0;
    rows[column] = row + 1;
    return {
      id: node.id,
      label: node.label,
      kind: node.kind,
      column,
      row,
      depth: column,
    };
  });
}

export function edgeSegments(
  dag: PlaybookDagV4,
  cells: DagCell[],
): EdgeSegment[] {
  const byId = new Map(cells.map((cell) => [cell.id, cell]));
  const segments: EdgeSegment[] = [];
  for (const node of dag.nodes) {
    for (const dependency of node.depends_on) {
      const from = byId.get(dependency);
      const to = byId.get(node.id);
      if (!from || !to) continue;
      segments.push({
        id: `${dependency}>${node.id}`,
        source: dependency,
        target: node.id,
        column: from.column + 1,
        row: from.row,
        span: Math.max(1, to.column - from.column),
        label: `${from.label} to ${to.label}`,
      });
    }
  }
  return segments.sort((a, b) => a.id.localeCompare(b.id));
}

export function traceSummary(trace: TraceStepV4[]): TraceSummary {
  const count = (status: string) =>
    trace.filter((step) => step.status === status).length;
  const durations = trace.map((step) => step.duration_ms);
  return {
    total: trace.length,
    succeeded: count("succeeded"),
    failed: count("failed"),
    skipped: count("skipped"),
    durationMs: durations.reduce((sum, value) => sum + value, 0),
    maxDurationMs: durations.length ? Math.max(...durations) : 1,
  };
}

export function scheduleLabel(schedule: ScheduleV4): string {
  const clock = `${String(schedule.hour).padStart(2, "0")}:${String(schedule.minute).padStart(2, "0")}`;
  switch (schedule.frequency) {
    case "interval":
      return `Every ${schedule.interval_minutes} minutes`;
    case "daily":
      return `Daily at ${clock}`;
    case "weekly":
      return `Weekly on ${schedule.day_of_week.join(", ") || "all days"} at ${clock}`;
    case "monthly":
      return `Monthly on day ${schedule.day_of_month} at ${clock}`;
    default:
      return "Custom recurrence";
  }
}

export function statusTone(status: RunStatusV4 | string): string {
  if (status === "succeeded") return "good";
  if (status === "failed") return "bad";
  if (status === "running") return "info";
  if (status === "cancelled") return "warn";
  return "neutral";
}

export function initialPlaybookAutomationState(
  dag: PlaybookDagV4 = {
    id: "pb-new",
    name: "Untitled",
    description: "",
    nodes: [],
    edges: [],
  },
): PlaybookAutomationState {
  return {
    dag,
    selectedNodeId: dag.nodes[0]?.id ?? "",
    validation: null,
    trace: [],
    runs: [],
    schedules: [],
    statusFilter: "",
    page: 1,
    busy: false,
    error: "",
  };
}

function replaceNode(dag: PlaybookDagV4, node: DagNodeV4): PlaybookDagV4 {
  const exists = dag.nodes.some((item) => item.id === node.id);
  return {
    ...dag,
    nodes: exists
      ? dag.nodes.map((item) => (item.id === node.id ? node : item))
      : [...dag.nodes, node],
  };
}

export function reducePlaybookAutomation(
  state: PlaybookAutomationState,
  action: PlaybookAutomationAction,
): PlaybookAutomationState {
  switch (action.type) {
    case "set-dag":
      return {
        ...state,
        dag: action.dag,
        selectedNodeId: action.dag.nodes.some(
          (node) => node.id === state.selectedNodeId,
        )
          ? state.selectedNodeId
          : (action.dag.nodes[0]?.id ?? ""),
        validation: null,
      };
    case "select-node":
      return { ...state, selectedNodeId: action.id };
    case "set-validation":
      return { ...state, validation: action.report };
    case "set-trace":
      return { ...state, trace: action.trace };
    case "set-runs":
      return { ...state, runs: action.runs };
    case "set-schedules":
      return { ...state, schedules: action.schedules };
    case "set-filter":
      return { ...state, statusFilter: action.status, page: 1 };
    case "set-page":
      return { ...state, page: Math.max(1, action.page) };
    case "set-busy":
      return { ...state, busy: action.busy };
    case "set-error":
      return { ...state, error: action.error };
    case "add-node":
      return {
        ...state,
        dag: replaceNode(state.dag, action.node),
        selectedNodeId: action.node.id,
      };
    case "remove-node":
      return {
        ...state,
        dag: {
          ...state.dag,
          nodes: state.dag.nodes.filter((node) => node.id !== action.id),
          edges: state.dag.edges.filter(
            (edge) => edge.source !== action.id && edge.target !== action.id,
          ),
        },
        selectedNodeId:
          state.selectedNodeId === action.id ? "" : state.selectedNodeId,
      };
    case "toggle-dependency": {
      if (action.from === action.to) return state;
      const node = state.dag.nodes.find((item) => item.id === action.to);
      if (!node) return state;
      const present = node.depends_on.includes(action.from);
      const updated: DagNodeV4 = {
        ...node,
        depends_on: present
          ? node.depends_on.filter((id) => id !== action.from)
          : [...node.depends_on, action.from],
      };
      return {
        ...state,
        dag: replaceNode(state.dag, updated),
        validation: null,
      };
    }
    case "update-schedule": {
      const exists = state.schedules.some(
        (item) => item.id === action.schedule.id,
      );
      return {
        ...state,
        schedules: exists
          ? state.schedules.map((item) =>
              item.id === action.schedule.id ? action.schedule : item,
            )
          : [...state.schedules, action.schedule],
      };
    }
    case "reset":
      return initialPlaybookAutomationState(state.dag);
    default:
      return state;
  }
}

export function visibleRuns(state: PlaybookAutomationState): RunRecordV4[] {
  if (!state.statusFilter) return state.runs;
  return state.runs.filter((run) => run.status === state.statusFilter);
}

export function selectedNode(state: PlaybookAutomationState): DagNodeV4 | null {
  return (
    state.dag.nodes.find((node) => node.id === state.selectedNodeId) ?? null
  );
}

export function canDryRun(state: PlaybookAutomationState): boolean {
  return (
    state.dag.nodes.length > 0 && !state.busy && state.validation?.ok !== false
  );
}
