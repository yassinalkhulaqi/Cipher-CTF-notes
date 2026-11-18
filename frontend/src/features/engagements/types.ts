export type EngagementStatus =
  | "planning"
  | "active"
  | "paused"
  | "reporting"
  | "closed"
  | "archived";

export type EngagementKind =
  | "pentest"
  | "red_team"
  | "ctf"
  | "lab"
  | "audit"
  | "research";

export type TargetKind =
  | "domain"
  | "ip_address"
  | "cidr"
  | "url"
  | "host"
  | "application"
  | "network"
  | "cloud";

export type TargetStatus =
  | "discovered"
  | "confirmed"
  | "tested"
  | "excluded"
  | "out_of_service";

export type ScopeStatus =
  | "unspecified"
  | "in_scope"
  | "out_of_scope"
  | "pending"
  | "waived";

export type Criticality =
  | "informational"
  | "low"
  | "medium"
  | "high"
  | "critical";

export type AssetKind =
  | "server"
  | "workstation"
  | "database"
  | "device"
  | "repository"
  | "container"
  | "cloud_resource"
  | "identity"
  | "unknown";

export type AssetStatus =
  | "identified"
  | "enumerated"
  | "assessed"
  | "remediated"
  | "decommissioned";

export type ServiceStatus =
  | "suspected"
  | "discovered"
  | "verified"
  | "tested"
  | "closed";

export type CredentialKind =
  | "password"
  | "api_token"
  | "ssh_key"
  | "certificate"
  | "cookie"
  | "hash";

export type CredentialStatus =
  | "candidate"
  | "valid"
  | "invalid"
  | "revoked"
  | "rotated";

export type FindingStatus =
  | "draft"
  | "open"
  | "verified"
  | "accepted_risk"
  | "duplicate"
  | "remediated"
  | "closed";

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type Confidence = "low" | "medium" | "high" | "confirmed";

export type ScopeRuleKind =
  | "domain"
  | "ip_address"
  | "cidr"
  | "url"
  | "port"
  | "keyword";

export type ScopeAction = "include" | "exclude";

export type Tone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "accent";

export interface EngagementSummary {
  id: number;
  key: string;
  name: string;
  client: string;
  description: string;
  kind: EngagementKind;
  status: EngagementStatus;
  owner: string;
  start_date: string;
  end_date: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  display_name?: string;
  counts?: EngagementCounts;
  allowed_actions?: string[];
}

export interface EngagementCounts {
  targets: number;
  assets: number;
  services: number;
  credentials: number;
  findings: number;
  scope_rules: number;
}

export interface Target {
  id: number;
  engagement_id: number;
  value: string;
  name: string;
  kind: TargetKind;
  description: string;
  status: TargetStatus;
  scope_status: ScopeStatus;
  criticality: Criticality;
  tags: string[];
  notes: string;
  created_at: string;
  updated_at: string;
  display_name?: string;
}

export interface Asset {
  id: number;
  engagement_id: number;
  target_id: number;
  name: string;
  kind: AssetKind;
  identifier: string;
  status: AssetStatus;
  criticality: Criticality;
  owner: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Service {
  id: number;
  engagement_id: number;
  target_id: number;
  asset_id: number;
  name: string;
  port: number;
  protocol: string;
  product: string;
  version: string;
  status: ServiceStatus;
  notes: string;
  created_at: string;
  updated_at: string;
  endpoint?: string;
}

export interface Credential {
  id: number;
  engagement_id: number;
  target_id: number;
  username: string;
  secret_ref: string;
  kind: CredentialKind;
  status: CredentialStatus;
  rotated_at: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface FindingEvent {
  at: string;
  actor: string;
  action: string;
  from_status: string;
  to_status: string;
  note: string;
}

export interface Finding {
  id: number;
  engagement_id: number;
  target_id: number;
  asset_id: number;
  service_id: number;
  title: string;
  summary: string;
  severity: Severity;
  confidence: Confidence;
  cvss_vector: string;
  cvss_score: number;
  cwe: string;
  cwes: string[];
  cves: string[];
  status: FindingStatus;
  duplicate_of: number;
  owner: string;
  impact: string;
  remediation: string;
  reproduction_steps: string;
  references: string[];
  tags: string[];
  transitions: FindingEvent[];
  resolved_at: string;
  created_at: string;
  updated_at: string;
  target_name?: string;
  canonical_title?: string;
  allowed_actions?: string[];
  duplicate_candidates?: DuplicateMatch[];
  cvss?: CvssBreakdown | null;
}

export interface CvssBreakdown {
  version: string;
  vector: string;
  score: number;
  severity: string;
  metrics: Record<string, { code: string; label: string }>;
  extras: Record<string, string>;
}

export interface DuplicateMatch {
  source_id: number;
  candidate_id: number;
  score: number;
  reasons: string[];
  fingerprint: string;
}

export interface ScopeRule {
  id: number;
  engagement_id: number;
  kind: ScopeRuleKind;
  value: string;
  action: ScopeAction;
  notes: string;
  created_at: string;
}

export interface ScopeEvaluation {
  engagement_id: number;
  value: string;
  decision: "included" | "excluded" | "unspecified";
  in_scope: boolean;
  matched: ScopeRule[];
}

export interface SeverityCount {
  severity: Severity;
  total: number;
  open: number;
  verified: number;
  closed: number;
}

export interface TargetCoverage {
  target_id: number;
  target_name: string;
  scope_status: string;
  criticality: string;
  score: number;
  level: "complete" | "good" | "partial" | "missing";
  asset_count: number;
  service_count: number;
  finding_count: number;
  verified_count: number;
  evidence_count: number;
  gaps: string[];
}

export interface CoverageReport {
  engagement_id: number;
  score: number;
  level: string;
  targets: TargetCoverage[];
  uncovered: number[];
  partial: number[];
  priority: number[];
  gaps: string[];
  percent: number;
  gap_summary: Array<{ gap: string; count: number }>;
  criticality_distribution: Record<string, number>;
  out_of_scope_count: number;
}

export interface EngagementRollup {
  engagement_id: number;
  name: string;
  status: string;
  kind: string;
  target_count: number;
  asset_count: number;
  service_count: number;
  credential_count: number;
  finding_count: number;
  open_finding_count: number;
  verified_count: number;
  duplicate_count: number;
  risk_score: number;
  risk_band: string;
  coverage_score: number;
  severity: SeverityCount[];
  status_counts: Record<string, number>;
  confidence_counts: Record<string, number>;
  top_findings: Array<Record<string, string | number>>;
  age_buckets: Record<string, number>;
}

export interface DashboardPayload {
  engagement: EngagementSummary;
  rollup: EngagementRollup;
  cards: Array<{ label: string; value: number | string; tone: Tone }>;
  coverage: CoverageReport;
  severity_matrix: Record<string, Record<string, number>>;
  duplicates: {
    total: number;
    clusters: number;
    duplicate_groups: number;
    duplicate_findings: number;
    groups: Array<{ ids: number[]; titles: string[]; severity: string }>;
  };
  age_buckets: Record<string, number>;
  recent_activity: Activity[];
}

export interface Activity {
  id: number;
  engagement_id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  summary: string;
  actor: string;
  created_at: string;
}

export interface PortfolioPayload {
  engagement_count: number;
  active_count: number;
  finding_count: number;
  open_finding_count: number;
  critical_count: number;
  risk_score: number;
  risk_band: string;
  severity: SeverityCount[];
  engagements: EngagementRollup[];
}

export interface WorkflowEdge {
  action: string;
  from: string;
  to: string;
  label: string;
  requires_note: boolean;
}

export interface Workflow {
  name: string;
  states: string[];
  actions: string[];
  edges: WorkflowEdge[];
}

export interface PageMeta {
  cursor?: string | null;
  next?: string | null;
  total?: number;
  limit?: number;
  has_more?: boolean;
}

export interface ListResponse<T> {
  items: T[];
  page: PageMeta;
}
