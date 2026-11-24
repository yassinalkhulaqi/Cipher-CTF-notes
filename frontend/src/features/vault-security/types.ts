/** Wire types for the V3 vault security namespace. */

export type VaultState = "uninitialized" | "locked" | "unlocked";
export type PostureLevel = "strong" | "fair" | "weak" | "critical";
export type Tone = "good" | "warn" | "bad" | "neutral";

export interface PostureCheck {
  id: string;
  label: string;
  passed: boolean;
  severity: "critical" | "high" | "medium" | "low";
  detail: string;
  remediation: string;
  weight: number;
}

export interface PostureReport {
  score: number;
  level: PostureLevel;
  passed: number;
  total: number;
  checks: PostureCheck[];
  gap_ids: string[];
  generated_at: number;
  warnings: string[];
  contains_secrets: boolean;
}

export interface VaultStatus {
  vault_id: string;
  state: VaultState;
  initialized: boolean;
  active_key_id: string;
  key_version: number;
  rotation_count: number;
  recovery_active: number;
  audit_total: number;
  posture: PostureReport;
}

export interface SetupResponse {
  vault_id: string;
  key_id: string;
  created_at: number;
  recovery_codes: string[];
}

export interface LockedResponse {
  state: "locked" | "unlocked";
  locked_at: number;
}

export interface UnlockResponse {
  state: VaultState;
  key_id: string;
  version: number;
  unlocked_at: number;
}

export interface RotationResponse {
  from_key_id: string;
  to_key_id: string;
  from_version: number;
  to_version: number;
  created_at: number;
  steps: string[];
  rotated_at: number;
  recovery_codes: string[];
}

export interface RecoveryResponse {
  code_id: string;
  key_id: string;
  redeemed_at: number;
  remaining_active: number;
  recovery_codes: string[];
}

export interface SecretPatternInfo {
  name: string;
  kind: string;
  severity: string;
  description: string;
  enabled: boolean;
  default_mode: string;
}

export interface PolicyRule {
  rule_id: string;
  pattern: string;
  mode: "mask" | "hash" | "remove";
  priority: number;
  enabled: boolean;
  reason: string;
}

export interface ConsentSnapshot {
  granted: string[];
  pending: string[];
}

export interface PolicySnapshot {
  patterns: SecretPatternInfo[];
  rules: PolicyRule[];
  consents: ConsentSnapshot;
  max_scan_chars: number;
}

export interface PolicyDecision {
  allowed: boolean;
  scope: string;
  requires_consent: boolean;
  redactions: number;
  matched_patterns: string[];
  reason: string;
}

export interface PolicyPreview {
  decision: PolicyDecision;
  preview: {
    text: string;
    matches: Array<{
      pattern: string;
      kind: string;
      severity: string;
      start: number;
      end: number;
      length: number;
    }>;
    applied_rules: string[];
    redactions: number;
  };
}

export interface AuditEntry {
  entry_id: string;
  action: string;
  outcome: string;
  actor: string;
  subject: string;
  timestamp: number;
  detail: Record<string, unknown>;
  request_id: string;
}

export interface AuditList {
  entries: AuditEntry[];
  total: number;
  filter: Record<string, unknown>;
  stats: {
    total: number;
    by_outcome: Record<string, number>;
    by_action: Record<string, number>;
  };
}

export interface AuditExportResponse {
  format: "json" | "jsonl";
  document: string;
}

export interface VaultEvent {
  kind: string;
  subject: string;
  actor: string;
  severity: string;
  payload: Record<string, unknown>;
  correlation_id: string;
  sequence: number;
  timestamp: number;
  request_id: string;
}

export interface ConsentScopeValue {
  value: "export_plaintext" | "share_external" | "ai_assist" | "log_content";
  label: string;
}
