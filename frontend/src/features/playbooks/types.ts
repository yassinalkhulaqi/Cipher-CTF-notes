export type PlaybookStatus = "draft" | "active" | "archived";
export type StepKind =
  | "action"
  | "checklist"
  | "command"
  | "decision"
  | "note"
  | "verification";
export type VariableKind =
  | "text"
  | "number"
  | "boolean"
  | "choice"
  | "secret"
  | "list";
export type RunStatus = "planned" | "running" | "completed" | "cancelled";
export type StepStatus =
  | "pending"
  | "ready"
  | "running"
  | "done"
  | "skipped"
  | "failed";
export type ChecklistState = "pending" | "done" | "skipped" | "blocked";
export type ConditionOperator =
  | "eq"
  | "ne"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "contains"
  | "not_contains"
  | "in"
  | "not_in"
  | "exists"
  | "not_exists"
  | "matches";

export type PlaybookValue = string | number | boolean | PlaybookValue[];
export type PlaybookValues = Record<string, PlaybookValue>;

export interface Issue {
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  path?: string;
}

export interface Condition {
  field: string;
  operator: ConditionOperator;
  value: PlaybookValue;
}

export interface ChecklistItem {
  id: string;
  label: string;
  detail: string;
  required: boolean;
  condition: Condition | null;
  tags: string[];
}

export interface VariableDefinition {
  key: string;
  label: string;
  kind: VariableKind;
  required: boolean;
  default: PlaybookValue;
  choices: string[];
  description: string;
  secret: boolean;
  pattern: string;
  minimum: number | null;
  maximum: number | null;
}

export interface PlaybookStep {
  id: string;
  title: string;
  kind: StepKind;
  summary: string;
  command_template: string;
  snippet_key?: string;
  checklist: ChecklistItem[];
  depends_on: string[];
  when: Condition[];
  variables: string[];
  optional: boolean;
  estimated_minutes: number;
  tags: string[];
  note?: string;
}

export interface Playbook {
  id: number;
  key: string;
  title: string;
  description: string;
  status: PlaybookStatus;
  category: string;
  tags: string[];
  version: string;
  steps: PlaybookStep[];
  variables: VariableDefinition[];
  owner: string;
  created_at: string;
  updated_at: string;
  references: string[];
}

export interface PlaybookSummary extends Omit<Playbook, "steps" | "variables"> {
  step_count?: number;
  checklist_count?: number;
}

export interface PlannedStep {
  id: string;
  title: string;
  kind: StepKind;
  command: string;
  checklist: ChecklistItem[];
  depends_on: string[];
  skipped: boolean;
  reason?: string;
  variables: string[];
  warnings: Issue[];
}

export interface RunPlan {
  playbook_key: string;
  version: string;
  values: PlaybookValues;
  steps: PlannedStep[];
  issues: Issue[];
  estimated_minutes: number;
  critical_path: string[];
  generated_at: string;
}

export interface RunEvent {
  id: number;
  run_id: number;
  step_id: string;
  status: string;
  message: string;
  output: string;
  at: string;
}

export interface RunState {
  id: number;
  playbook_key: string;
  version: string;
  status: RunStatus;
  values: PlaybookValues;
  step_status: Record<string, StepStatus>;
  checklist: Record<string, ChecklistState>;
  notes: Record<string, string>;
  events: RunEvent[];
  current_step: string;
  started_at: string;
  updated_at: string;
  finished_at: string;
  context: Record<string, unknown>;
}

export interface StepAdvice {
  run_id: number;
  step_id: string;
  title: string;
  command: string;
  reason: string;
  checklist: ChecklistItem[];
  blocked_by: string[];
}

export interface SnippetRecord {
  id: number;
  key: string;
  title: string;
  command: string;
  description: string;
  tags: string[];
  library: string;
  variables: string[];
  usage_count: number;
  version: string;
  created_at: string;
  updated_at: string;
}

export interface TemplateRecord {
  id: number;
  key: string;
  name: string;
  content: string;
  description: string;
  tags: string[];
  category: string;
  variables: VariableDefinition[];
  version: string;
  changelog: string[];
  default_title: string;
}

export interface TemplatePreview {
  key: string;
  version: string;
  content: string;
  used: string[];
  unresolved: string[];
  warnings: Issue[];
}

export interface Recommendation {
  kind: "playbook" | "snippet" | "template";
  key: string;
  score: number;
  reason: string;
  title: string;
  meta: Record<string, unknown>;
}

export interface PageMeta {
  next_cursor?: string | null;
  has_more?: boolean;
  total?: number;
}

export interface Page<T> {
  items: T[];
  page?: PageMeta;
  etag?: string | null;
}

export interface GraphData {
  key: string;
  order: string[];
  layers: string[][];
  cycles: string[][];
  critical_path: string[];
  depth: number;
}

export interface StepGraphData {
  key: string;
  step_id: string;
  ancestors: string[];
  descendants: string[];
  dependencies: string[];
  dependents: string[];
}

export interface RunProgress {
  run_id: number;
  status: RunStatus;
  total: number;
  settled: number;
  percent: number;
  step_status: Record<string, StepStatus>;
  current_step: string;
  checklist?: ChecklistProgress;
}

export interface ChecklistProgress {
  total: number;
  done: number;
  required_total: number;
  required_done: number;
  percent: number;
  items: Array<{
    id: string;
    step_id: string;
    title: string;
    state: ChecklistState;
    required: boolean;
    note: string;
  }>;
}

export interface SnippetUsage {
  key: string;
  command: string;
  variables: string[];
  warnings: Issue[];
}

export interface BundlePayload {
  kind: string;
  schema_version: string;
  exported_at: string;
  source: string;
  playbooks: Record<string, unknown>[];
  snippets: Record<string, unknown>[];
  templates: Record<string, unknown>[];
  runs: Record<string, unknown>[];
  manifest: Record<string, unknown>;
  checksum: string;
}

export interface ImportReport {
  playbooks: string[];
  snippets: string[];
  templates: string[];
  runs: number[];
  conflicts: string[];
  renamed: string[];
  issues: Issue[];
  ok: boolean;
}
