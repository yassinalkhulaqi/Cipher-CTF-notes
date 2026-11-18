import { V2Client } from "../../lib/apiClient";
import type {
  AccessPolicy,
  AuditReport,
  CommandSafety,
  ConsentSummary,
  DashboardInput,
  DerivedKeyResult,
  EncryptedPayload,
  PolicyEvaluation,
  PrivacyMode,
  RedactionSummary,
  RiskAssessment,
  ScrubResult,
  SecretScanResult,
  SecurityDashboard,
  SecurityHealth,
  UrlSafety,
} from "./types";

export interface SecurityClientOptions {
  client?: V2Client;
}

export class SecurityClient {
  readonly routes = {
    health: "security.health",
    secretPatterns: "security.secret_patterns",
    scanSecrets: "security.scan_secrets",
    scanPayload: "security.scan_payload",
    redactionRules: "security.redaction_rules",
    redactText: "security.redact_text",
    redactPayload: "security.redact_payload",
    deriveKey: "security.derive_key",
    encryptText: "security.encrypt_text",
    decryptText: "security.decrypt_text",
    privacyLevels: "security.privacy_levels",
    privacyMode: "security.privacy_mode",
    consentFlags: "security.consent_flags",
    consentSummary: "security.consent_summary",
    policyDefaults: "security.policy_defaults",
    evaluateAccess: "security.evaluate_access",
    auditAnalyze: "security.audit_analyze",
    scrubText: "security.scrub_text",
    scrubExport: "security.scrub_export",
    checkUrl: "security.check_url",
    checkCommand: "security.check_command",
    assessRisk: "security.assess_risk",
    securityDashboard: "security.security_dashboard",
  } as const;

  constructor(private readonly options: SecurityClientOptions = {}) {}

  private get client(): V2Client {
    if (!this.options.client) {
      throw new Error("SecurityClient requires a V2Client instance");
    }
    return this.options.client;
  }

  health(): Promise<SecurityHealth> {
    return this.client.call<SecurityHealth>(this.routes.health);
  }

  secretPatterns(): Promise<{ patterns: Array<Record<string, unknown>> }> {
    return this.client.call(this.routes.secretPatterns);
  }

  scanSecrets(body: {
    text: string;
    patterns?: string[];
    include_entropy?: boolean;
    context_radius?: number;
    max_findings?: number;
  }): Promise<SecretScanResult> {
    return this.client.call<SecretScanResult>(this.routes.scanSecrets, body);
  }

  scanPayload(body: {
    payload: Record<string, unknown>;
    keys?: string[];
    patterns?: string[];
  }): Promise<{
    count: number;
    highest_severity: string;
    fields: Record<string, unknown>;
  }> {
    return this.client.call(this.routes.scanPayload, body);
  }

  redactionRules(): Promise<{ rules: Array<Record<string, unknown>> }> {
    return this.client.call(this.routes.redactionRules);
  }

  redactText(body: {
    text: string;
    scopes?: string[];
    rules?: Array<Record<string, unknown>>;
  }): Promise<RedactionSummary> {
    return this.client.call<RedactionSummary>(this.routes.redactText, body);
  }

  redactPayload(body: {
    payload: Record<string, unknown>;
    keys?: string[];
    rules?: Array<Record<string, unknown>>;
  }): Promise<{
    data: Record<string, unknown>;
    total_replacements: number;
    fields: Record<string, unknown>;
  }> {
    return this.client.call(this.routes.redactPayload, body);
  }

  deriveKey(body: {
    passphrase: string;
    salt?: string;
    iterations?: number;
    length?: number;
    salt_bytes?: number;
    digest?: string;
  }): Promise<DerivedKeyResult> {
    return this.client.call<DerivedKeyResult>(this.routes.deriveKey, body);
  }

  encryptText(body: {
    text: string;
    passphrase: string;
    iterations?: number;
    length?: number;
    salt_bytes?: number;
    associated_data?: string;
  }): Promise<{ payload: EncryptedPayload }> {
    return this.client.call(this.routes.encryptText, body);
  }

  decryptText(body: {
    payload: EncryptedPayload | Record<string, unknown> | string;
    passphrase: string;
    associated_data?: string;
  }): Promise<{ text: string }> {
    return this.client.call(this.routes.decryptText, body);
  }

  privacyLevels(): Promise<{ levels: PrivacyMode[] }> {
    return this.client.call(this.routes.privacyLevels);
  }

  privacyMode(
    body: { level?: string; overrides?: Record<string, boolean> } = {},
  ): Promise<PrivacyMode> {
    return this.client.call<PrivacyMode>(this.routes.privacyMode, body);
  }

  consentFlags(): Promise<ConsentSummary> {
    return this.client.call<ConsentSummary>(this.routes.consentFlags);
  }

  consentSummary(
    body: { decisions?: Record<string, boolean>; flags?: unknown[] } = {},
  ): Promise<ConsentSummary> {
    return this.client.call<ConsentSummary>(this.routes.consentSummary, body);
  }

  policyDefaults(): Promise<AccessPolicy> {
    return this.client.call<AccessPolicy>(this.routes.policyDefaults);
  }

  evaluateAccess(body: {
    action: string;
    role?: string;
    resource?: string;
    context?: Record<string, unknown>;
    policy?: AccessPolicy | Record<string, unknown>;
  }): Promise<PolicyEvaluation> {
    return this.client.call<PolicyEvaluation>(this.routes.evaluateAccess, body);
  }

  auditAnalyze(
    body: {
      events?: Array<Record<string, unknown>>;
      failure_threshold?: number;
      window_minutes?: number;
    } = {},
  ): Promise<AuditReport> {
    return this.client.call<AuditReport>(this.routes.auditAnalyze, body);
  }

  scrubText(body: {
    text: string;
    policy?: Record<string, unknown>;
    rules?: Array<Record<string, unknown>>;
  }): Promise<ScrubResult> {
    return this.client.call<ScrubResult>(this.routes.scrubText, body);
  }

  scrubExport(body: {
    payload: Record<string, unknown>;
    policy?: Record<string, unknown>;
    rules?: Array<Record<string, unknown>>;
  }): Promise<ScrubResult> {
    return this.client.call<ScrubResult>(this.routes.scrubExport, body);
  }

  checkUrl(body: {
    url: string;
    allow_localhost?: boolean;
    allow_private_networks?: boolean;
    allowed_schemes?: string[];
  }): Promise<UrlSafety> {
    return this.client.call<UrlSafety>(this.routes.checkUrl, body);
  }

  checkCommand(body: { command: string }): Promise<CommandSafety> {
    return this.client.call<CommandSafety>(this.routes.checkCommand, body);
  }

  assessRisk(body: Record<string, unknown> = {}): Promise<RiskAssessment> {
    return this.client.call<RiskAssessment>(this.routes.assessRisk, body);
  }

  securityDashboard(body: DashboardInput = {}): Promise<SecurityDashboard> {
    return this.client.call<SecurityDashboard>(
      this.routes.securityDashboard,
      body,
    );
  }
}

export function createSecurityClient(client: V2Client): SecurityClient {
  return new SecurityClient({ client });
}
