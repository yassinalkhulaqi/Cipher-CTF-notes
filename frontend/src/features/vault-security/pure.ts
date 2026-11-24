/** Pure helpers for the vault security feature (no network, no side effects). */

import type {
  AuditEntry,
  AuditList,
  ConsentScopeValue,
  PolicyRule,
  PolicySnapshot,
  PostureCheck,
  PostureLevel,
  PostureReport,
  Tone,
  VaultState,
} from "./types";

export const CONSENT_SCOPES: ConsentScopeValue[] = [
  { value: "export_plaintext", label: "Plaintext export" },
  { value: "share_external", label: "External sharing" },
  { value: "ai_assist", label: "AI assistance" },
  { value: "log_content", label: "Content logging" },
];

export function postureTone(level: PostureLevel): Tone {
  switch (level) {
    case "strong":
      return "good";
    case "fair":
      return "warn";
    case "weak":
    case "critical":
      return "bad";
    default:
      return "neutral";
  }
}

export function posturePercent(score: number): number {
  if (!Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

export function gapSummary(report: PostureReport): string {
  if (report.gap_ids.length === 0) return "All security checks pass";
  return `${report.gap_ids.length} gap${report.gap_ids.length === 1 ? "" : "s"} to resolve`;
}

export function severityTone(severity: PostureCheck["severity"]): Tone {
  if (severity === "critical" || severity === "high") return "bad";
  if (severity === "medium") return "warn";
  return "neutral";
}

export function sortedChecks(report: PostureReport): PostureCheck[] {
  const rank: Record<PostureCheck["severity"], number> = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };
  return [...report.checks].sort(
    (a, b) =>
      Number(a.passed) - Number(b.passed) ||
      rank[a.severity] - rank[b.severity] ||
      a.id.localeCompare(b.id),
  );
}

export function maskRecoveryCode(code: string): string {
  const groups = code.split("-").filter(Boolean);
  if (groups.length === 0) return "[hidden]";
  return `${groups[0]}-•••••-•••••`;
}

export function formatTimestamp(timestamp: number): string {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "unknown";
  return new Date(timestamp * 1000).toISOString().slice(0, 19).replace("T", " ");
}

export interface PassphraseCheck {
  valid: boolean;
  reason: string;
}

export function checkPassphrase(value: string, confirmation = value): PassphraseCheck {
  if (value.length < 12) {
    return { valid: false, reason: "Use at least 12 characters" };
  }
  if (value !== value.trim()) {
    return { valid: false, reason: "Remove leading and trailing spaces" };
  }
  if (value !== confirmation) {
    return { valid: false, reason: "Passphrases do not match" };
  }
  return { valid: true, reason: "Passphrase looks strong enough" };
}

export interface WizardStep {
  id: "confirm" | "passphrase" | "codes";
  label: string;
  complete: boolean;
}

export function wizardSteps(state: VaultState, codes: string[]): WizardStep[] {
  return [
    { id: "confirm", label: "Confirm setup", complete: state !== "uninitialized" },
    {
      id: "passphrase",
      label: "Choose a passphrase",
      complete: state !== "uninitialized",
    },
    {
      id: "codes",
      label: "Save recovery codes",
      complete: codes.length > 0,
    },
  ];
}

export function needsSetup(state: VaultState): boolean {
  return state === "uninitialized";
}

export function needsUnlock(state: VaultState): boolean {
  return state === "locked";
}

export function canShowContent(state: VaultState): boolean {
  return state === "unlocked";
}

export function lockedMessage(state: VaultState): string {
  if (state === "uninitialized") return "Encryption is not configured yet";
  if (state === "locked") return "Vault locked - unlock to view content";
  return "Vault unlocked - lock when finished";
}

export function safeErrorText(message: string): string {
  const trimmed = message.trim();
  if (!trimmed) return "The request could not be completed";
  if (/passphrase|password|recovery code/i.test(trimmed)) {
    return "Verification failed. Check your credentials and try again.";
  }
  return trimmed.slice(0, 200);
}

export interface AuditFilterState {
  action: string;
  outcome: string;
  actor: string;
  limit: number;
}

export function filterAudit(entries: AuditEntry[], filter: AuditFilterState): AuditEntry[] {
  const action = filter.action.trim().toLowerCase();
  const outcome = filter.outcome.trim().toLowerCase();
  const actor = filter.actor.trim().toLowerCase();
  const limit = Math.max(1, Math.min(200, Math.floor(filter.limit) || 50));
  return entries
    .filter((entry) => !action || entry.action.toLowerCase().includes(action))
    .filter((entry) => !outcome || entry.outcome.toLowerCase() === outcome)
    .filter((entry) => !actor || entry.actor.toLowerCase().includes(actor))
    .slice(0, limit);
}

export function auditCounts(list: AuditList): { success: number; denied: number; other: number } {
  let success = 0;
  let denied = 0;
  for (const entry of list.entries) {
    if (entry.outcome === "success") success += 1;
    else if (entry.outcome === "denied") denied += 1;
  }
  return { success, denied, other: list.entries.length - success - denied };
}

export function effectiveRules(
  snapshot: PolicySnapshot,
): Array<PolicyRule & { effective: boolean; precedence: number }> {
  const enabled = snapshot.rules.filter((rule) => rule.enabled);
  const patterns = new Set(snapshot.patterns.map((pattern) => pattern.name));
  return enabled
    .map((rule) => ({
      ...rule,
      effective: rule.pattern === "*" || patterns.has(rule.pattern),
      precedence: rule.priority,
    }))
    .sort((a, b) => b.precedence - a.precedence || a.rule_id.localeCompare(b.rule_id));
}

export function consentLabel(scope: ConsentScopeValue, granted: boolean): string {
  return `${scope.label}: ${granted ? "granted" : "not granted"}`;
}

export function redactionNotice(redactions: number): string {
  if (redactions === 0) return "No secrets detected in this preview";
  return `${redactions} secret value${redactions === 1 ? "" : "s"} redacted before display`;
}

export function recoveryWarning(codes: string[]): string {
  if (codes.length === 0) return "No recovery codes are displayed";
  return `Store ${codes.length} recovery codes offline; they are shown only once`;
}

export function printableCodes(codes: string[]): string {
  return codes.join("\n");
}
