/** Wire types for the V3 activity namespace. */

export type DensityMode = "compact" | "comfortable" | "detailed";
export type DigestPeriod = "daily" | "weekly";
export type ActivitySeverity =
  | "trace"
  | "info"
  | "notice"
  | "warning"
  | "critical";
export type FilterOperator = "include" | "exclude";

export interface JumpTarget {
  ref: string;
  kind: string;
  value: string;
  label: string;
  route: string;
  resolvable: boolean;
}

export interface ActivityEntry {
  sequence: number;
  kind: string;
  title: string;
  summary: string;
  actor: string;
  severity: ActivitySeverity;
  timestamp: number;
  iso_timestamp: string;
  date_key: string;
  week_key?: string;
  subject_ref: string;
  payload?: Record<string, unknown>;
  jump: JumpTarget | null;
  correlation_id?: string;
  request_id?: string;
  tags?: string[];
  redactions: string[];
}

export interface DateGroup {
  key: string;
  label: string;
  period: DigestPeriod | string;
  count: number;
  entries: ActivityEntry[];
}

export interface FacetCounts {
  kinds: Record<string, number>;
  actors: Record<string, number>;
  severities: Record<string, number>;
  subjects: Record<string, number>;
}

export interface ActivityPage {
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface StreamResult {
  entries: ActivityEntry[];
  total: number;
  groups: DateGroup[];
  facets: FacetCounts;
  page: ActivityPage | null;
  query: string;
  density: DensityMode;
  timezone: string;
  warnings: string[];
}

export interface FilterChipData {
  key: string;
  value: string;
  operator: FilterOperator;
  label: string;
  token: string;
}

export interface FilterDefinition {
  key: string;
  label: string;
  description: string;
  choices: string[];
  multi: boolean;
}

export interface FilterMetadata {
  keys: FilterDefinition[];
  operators: string[];
  grammar: string;
}

export interface FilterValidation {
  valid: boolean;
  errors: string[];
  tokens: FilterChipData[];
  normalized: string;
}

export interface DigestSection {
  title: string;
  kind: string;
  count: number;
  entries: ActivityEntry[];
}

export interface Digest {
  period: DigestPeriod;
  key: string;
  label: string;
  start: number;
  end: number;
  iso_start: string;
  iso_end: string;
  timezone: string;
  entry_count: number;
  counts: Record<string, number>;
  actor_counts: Record<string, number>;
  sections: DigestSection[];
  highlights: ActivityEntry[];
}

export interface DigestCollection {
  period: DigestPeriod;
  timezone: string;
  generated_at: number;
  total_events: number;
  digests: Digest[];
}

export interface VisitMarker {
  identity: string;
  timestamp: number;
  sequence: number;
  iso_timestamp: string;
  note: string;
}

export interface SinceLastVisit {
  identity: string;
  marker: VisitMarker | null;
  count: number;
  by_kind: Record<string, number>;
  by_severity: Record<string, number>;
  first_timestamp: number | null;
  last_timestamp: number | null;
  entries: ActivityEntry[];
}

export interface DayCount {
  date_key: string;
  count: number;
}

export interface RankedValue {
  value: string;
  count: number;
}

export interface RetrospectiveSummary {
  start: number;
  end: number;
  iso_start: string;
  iso_end: string;
  timezone: string;
  total_events: number;
  active_days: number;
  active_weeks: number;
  longest_streak: number;
  trailing_streak: number;
  busiest_day: DayCount | null;
  top_kinds: RankedValue[];
  top_actors: RankedValue[];
  top_subjects: RankedValue[];
  severity_mix: Record<string, number>;
  highlights: ActivityEntry[];
  daily_counts: DayCount[];
}

export interface RedactionReportData {
  applied: boolean;
  redacted_keys: string[];
  rewritten_values: number;
  dropped_depth: number;
  keys_inspected: number;
}

export interface ActivityStats {
  entries: number;
  sequences: number[];
  kinds: Record<string, number>;
  severities: Record<string, number>;
  visitors: string[];
  bus_errors: number;
  redactions: RedactionReportData;
  timezone: string;
}

export interface ActivityHealth {
  status: string;
  namespace: string;
  entries: number;
  timezone: string;
}

export interface ActivityModes {
  densities: DensityMode[];
  periods: DigestPeriod[];
}

export interface ResolvedEntry {
  entry: ActivityEntry;
  target: JumpTarget | null;
}

export const EMPTY_FACETS: FacetCounts = {
  kinds: {},
  actors: {},
  severities: {},
  subjects: {},
};

export const EMPTY_STREAM: StreamResult = {
  entries: [],
  total: 0,
  groups: [],
  facets: EMPTY_FACETS,
  page: null,
  query: "",
  density: "comfortable",
  timezone: "UTC",
  warnings: [],
};
