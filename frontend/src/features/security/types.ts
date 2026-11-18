export type Severity = "none" | "info" | "low" | "medium" | "high" | "critical";

export interface SecretPattern {
  name: string;
  regex: string;
  severity: Severity;
  description: string;
  tags: string[];
  entropy_hint: number;
}

export interface SecretFinding {
  name: string;
  severity: Severity;
  start: number;
  end: number;
  line: number;
  column: number;
  length: number;
  value: string;
  masked: string;
  confidence: number;
  tags: string[];
  context: string;
}

export interface SecretScanResult {
  count: number;
  highest_severity: Severity;
  scanned_characters: number;
  scanned_lines: number;
  pattern_count: number;
  entropy_flagged: number;
  by_name: Record<string, number>;
  findings: SecretFinding[];
}

export interface RedactionRule {
  name: string;
  regex?: string;
  pattern?: string;
  replacement: string;
  description?: string;
  scope?: string;
  priority?: number;
  enabled?: boolean;
  tags?: string[];
  flags?: string[];
}

export interface RedactionSummary {
  text: string;
  applied: string[];
  counts: Record<string, number>;
  total_replacements: number;
}

export interface PrivacyControl {
  key: string;
  label: string;
  enabled: boolean;
  category: string;
}

export interface PrivacyMode {
  level: string;
  label?: string;
  description?: string;
  redact_secrets: boolean;
  mask_identifiers: boolean;
  allow_external_links: boolean;
  allow_command_copy: boolean;
  scrub_exports: boolean;
  require_export_consent: boolean;
  retain_audit_details: boolean;
  share_telemetry: boolean;
  rank: number;
  controls: PrivacyControl[];
  customized?: boolean;
}

export interface ConsentFlag {
  key: string;
  label: string;
  description: string;
  required_for: string[];
  default: boolean;
  sensitive: boolean;
}

export interface ConsentDecision {
  key: string;
  granted: boolean;
  source: string;
  recorded_at: string;
  note: string;
}

export interface ConsentItem {
  flag: ConsentFlag;
  decision: ConsentDecision;
  granted: boolean;
}

export interface ConsentSummary {
  total: number;
  granted: number;
  denied: number;
  items: ConsentItem[];
  flags?: ConsentFlag[];
  context?: Record<string, boolean>;
}

export interface PolicyRule {
  name: string;
  effect: "allow" | "deny";
  actions: string[];
  roles: string[];
  resources: string[];
  conditions: Record<string, unknown>;
  priority: number;
  reason: string;
}

export interface AccessPolicy {
  name: string;
  description: string;
  default_decision: "allow" | "deny" | "review";
  rules: PolicyRule[];
}

export interface PolicyEvaluation {
  decision: "allow" | "deny" | "review";
  allowed: boolean;
  matched_rules: string[];
  reasons: string[];
  action: string;
  role: string;
  resource: string;
}

export interface AuditFinding {
  code: string;
  severity: Severity;
  message: string;
  count: number;
  event_ids: string[];
  details: Record<string, unknown>;
}

export interface AuditReport {
  total_events: number;
  highest_severity: Severity;
  counts_by_type: Record<string, number>;
  counts_by_outcome: Record<string, number>;
  timeline: Array<Record<string, unknown>>;
  findings: AuditFinding[];
}

export interface UrlSafety {
  url: string;
  safe: boolean;
  scheme: string;
  host: string;
  reasons: string[];
  risk: Severity;
}

export interface CommandSafety {
  command: string;
  safe: boolean;
  risk: Severity;
  reasons: string[];
  tokens: string[];
  destructive: boolean;
  networked: boolean;
  privileged: boolean;
}

export interface RiskFactor {
  name: string;
  score: number;
  weight: number;
  weighted_score: number;
  severity: Severity;
  details: Record<string, unknown>;
}

export interface RiskScore {
  score: number;
  level: Severity;
  confidence: number;
}

export interface RiskAssessment {
  score: RiskScore;
  factors: RiskFactor[];
  recommendations: string[];
}

export interface ScrubReport {
  removed_keys: string[];
  masked_keys: string[];
  redacted_fields: string[];
  redaction_counts: Record<string, number>;
  total_redactions: number;
}

export interface ScrubResult {
  payload?: Record<string, unknown>;
  text?: string;
  report?: ScrubReport;
  redaction?: RedactionSummary;
}

export interface SecurityDashboard {
  privacy: PrivacyMode;
  consent: Record<string, boolean>;
  secrets: SecretScanResult;
  audit: AuditReport;
  urls: UrlSafety[];
  commands: CommandSafety[];
  scrub: ScrubResult | null;
  risk: RiskAssessment;
  safe_link_policy: {
    allow_external_links: boolean;
    allow_command_copy: boolean;
  };
}

export interface SecurityHealth {
  ok: boolean;
  namespace: string;
  features: string[];
  secret_patterns: number;
  redaction_rules: number;
  privacy_levels: string[];
}

export interface ScanFilters {
  includeEntropy: boolean;
  maxFindings: number;
  contextRadius: number;
  selectedPatterns: string[];
}

export interface RedactionOptions {
  scopes?: string[];
  rules?: RedactionRule[];
}

export interface DerivedKeyResult {
  derived: boolean;
  fingerprint: string;
  salt: string;
  params: Record<string, unknown>;
}

export interface EncryptedPayload {
  magic: string;
  version: number;
  salt: string;
  nonce: string;
  ciphertext: string;
  tag: string;
  kdf: Record<string, unknown>;
}

export interface SecuritySettingsState {
  privacyLevel: string;
  overrides: Record<string, boolean>;
  consent: Record<string, boolean>;
  allowLocalhostLinks: boolean;
  allowPrivateNetworkLinks: boolean;
}

export interface DashboardInput {
  [key: string]: unknown;
  text?: string;
  events?: Array<Record<string, unknown>>;
  privacy_level?: string;
  consent?: Record<string, boolean>;
  urls?: string[];
  commands?: string[];
  export_payload?: Record<string, unknown>;
}
