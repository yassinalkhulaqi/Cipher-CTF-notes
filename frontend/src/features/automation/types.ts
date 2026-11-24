/** Wire types for the V3 automation namespace. */

export type StepKind =
  | "create_note"
  | "create_finding"
  | "attach_evidence"
  | "render_section"
  | "emit_event";

export type VariableKind =
  | "text"
  | "number"
  | "boolean"
  | "choice"
  | "list"
  | "entity_ref";

export type ConditionOperator =
  | "eq"
  | "ne"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "contains"
  | "exists"
  | "not_exists"
  | "in";

export type Frequency = "hourly" | "daily" | "weekly" | "monthly";

export interface VariableDef {
  key: string;
  kind: VariableKind;
  label?: string;
  required?: boolean;
  default?: unknown;
  choices?: string[];
  description?: string;
  secret?: boolean;
  pattern?: string;
  minimum?: number;
  maximum?: number;
}

export interface StepGuard {
  field: string;
  operator: ConditionOperator;
  value?: unknown;
}

export interface StepDef {
  id: string;
  title: string;
  kind: StepKind;
  depends_on?: string[];
  inputs?: Record<string, unknown>;
  condition?: StepGuard | null;
  output?: string;
  optional?: boolean;
  tags?: string[];
}

export interface RecurrenceRule {
  frequency: Frequency;
  interval: number;
  by_weekday?: number[];
  by_month_day?: number | null;
  hour: number;
  minute: number;
  start_at?: number;
  end_at?: number;
  count?: number;
}

export interface Playbook {
  id: string;
  title: string;
  description?: string;
  version?: number;
  tags?: string[];
  variables: VariableDef[];
  steps: StepDef[];
  recurrence?: RecurrenceRule | null;
}

export interface ValidationIssue {
  code: string;
  message: string;
  path: string;
  severity: "error" | "warning";
}

export interface VariableResolution {
  values: Record<string, unknown>;
  issues: ValidationIssue[];
  ok: boolean;
}

export interface DagCompilation {
  order: string[];
  layers: string[][];
  cycles: string[][];
  duplicates: string[];
  missing: string[];
  self_dependencies: string[];
  critical_path: string[];
  depth: Record<string, number>;
  issues: ValidationIssue[];
  ok: boolean;
}

export interface MutationIntent {
  step_id: string;
  kind: StepKind;
  target: string;
  payload: Record<string, unknown>;
  key: string;
  inverse: Record<string, unknown>;
}

export interface MutationResult {
  intent: MutationIntent;
  ref: string;
  applied: boolean;
  before?: unknown;
  after?: unknown;
}

export interface TraceEntry {
  index: number;
  step_id: string;
  status: "planned" | "executed" | "skipped" | "failed";
  kind: StepKind;
  message: string;
  variables?: Record<string, unknown>;
  result?: MutationResult | null;
  chain?: string;
}

export interface DryRunTrace {
  playbook_ref: string;
  mode: "dry_run" | "live";
  entries: TraceEntry[];
  variables: Record<string, unknown>;
  digest: string;
  writes: number;
  input_fingerprint: string;
  state_digest: string;
}

export type RunStatus = "planned" | "completed" | "rolled_back" | "failed";

export interface RunRecord {
  id: string;
  playbook_ref: string;
  status: RunStatus;
  mode: "dry_run" | "live";
  started_at: number;
  finished_at: number;
  trace: TraceEntry[];
  variables: Record<string, unknown>;
  trace_digest: string;
  state_digest: string;
  rollback_of: string;
  input_fingerprint: string;
}

export interface DiffEntry {
  path: string;
  before: unknown;
  after: unknown;
}

export interface TimelineItem {
  index: number;
  step_id: string;
  title: string;
  status: string;
  kind: StepKind;
  message: string;
  target: string;
  mutation: MutationIntent | null;
  tone: "good" | "info" | "warn" | "bad" | "neutral";
  chain: string;
}

export const STEP_LABELS: Record<StepKind, string> = {
  create_note: "Create note",
  create_finding: "Create finding",
  attach_evidence: "Attach evidence",
  render_section: "Render section",
  emit_event: "Emit event",
};

export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function issue(
  code: string,
  message: string,
  path = "",
  severity: "error" | "warning" = "error",
): ValidationIssue {
  return { code, message, path, severity };
}
