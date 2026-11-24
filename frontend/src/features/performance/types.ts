/** Shared view models for the performance feature. */

export type PerfTone = "neutral" | "good" | "warn" | "bad";

export interface VirtualWindow {
  start: number;
  end: number;
  offsetTop: number;
  totalHeight: number;
  rendered: number;
}

export interface TreeRow {
  key: string;
  label: string;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
  parent: string;
  kind: string;
  count: number;
}

export interface TreeSource {
  key: string;
  label: string;
  kind: string;
  count: number;
  children?: TreeSource[];
}

export interface HudMetric {
  label: string;
  value: string;
  detail: string;
  tone: PerfTone;
}

export interface FrameStats {
  samples: number;
  average: number;
  p95: number;
  worst: number;
  tone: PerfTone;
}

export interface BudgetView {
  name: string;
  measured: number;
  limit: number;
  passed: boolean;
  metric: string;
}

export interface IndexFreshness {
  generation: number;
  indexedGeneration: number;
  lastIndexedAt: number;
  observedAt: number;
  lagSeconds: number;
  stale: boolean;
}

export interface DeferredTask<T> {
  id: string;
  label: string;
  cost: number;
  payload: T;
}

export interface DeferredChunk<T> {
  index: number;
  tasks: DeferredTask<T>[];
  cost: number;
}

export interface FixtureSummary {
  notes: number;
  findings: number;
  evidence: number;
  events: number;
  fingerprint: string;
}

export interface PerfSnapshot {
  fixture: FixtureSummary;
  budgets: BudgetView[];
  digest: string;
  wallMs: number;
  freshness: IndexFreshness;
  frames: FrameStats;
}

export interface ColumnSpec<T> {
  key: string;
  title: string;
  width: number;
  render: (row: T) => string;
}
