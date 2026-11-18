import assert from "node:assert/strict";
import test from "node:test";
import { V2Client } from "../src/lib/apiClient";
import {
  SecurityClient,
  createSecurityClient,
} from "../src/features/security/client";
import {
  auditSeverityCounts,
  compareSeverity,
  consentProgress,
  dashboardAlerts,
  dashboardStatus,
  filterFindings,
  formatConfidence,
  formatCount,
  formatScore,
  groupFindingsByName,
  maskIfNeeded,
  maxSeverity,
  mergeConsent,
  normalizeSeverity,
  privacyControlMap,
  redactPreviewLabel,
  redactionSummaryText,
  riskGaugePercent,
  riskHeadline,
  riskTone,
  safetyReasonsText,
  scanSummary,
  severityLabel,
  sortAuditFindings,
  sortFindings,
  topRiskFactors,
} from "../src/features/security/helpers";
import {
  formatCommandPreview,
  isExternalUrl,
  parseUrl,
  redactUrlForDisplay,
  safeLinkAttributes,
  safeLinkDecision,
  safeCommandDecision,
  sanitizeHref,
  truncateMiddle,
} from "../src/features/security/safeLink";
import type {
  AuditReport,
  CommandSafety,
  PrivacyMode,
  RedactionSummary,
  RiskAssessment,
  SecretFinding,
  SecretScanResult,
  SecurityDashboard,
  UrlSafety,
} from "../src/features/security/types";

interface FetchCall {
  url: string;
  body: Record<string, unknown>;
}

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({ ok: true, data }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function bodyOf(init: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init.body ?? "{}")) as Record<string, unknown>;
}

function routeOf(url: string): string {
  return url.slice(url.lastIndexOf("/") + 1);
}

function fakeClient(
  handler: (route: string, body: Record<string, unknown>) => unknown,
): { client: SecurityClient; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const fetch = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const body = bodyOf(init);
    calls.push({ url, body });
    return envelope(handler(routeOf(url), body));
  }) as typeof globalThis.fetch;
  return {
    client: new SecurityClient({
      client: new V2Client({ fetch, requestId: () => "req_security" }),
    }),
    calls,
  };
}

function finding(overrides: Partial<SecretFinding> = {}): SecretFinding {
  return {
    name: "github_token",
    severity: "high",
    start: 0,
    end: 10,
    line: 1,
    column: 1,
    length: 10,
    value: "ghp_secret",
    masked: "ghp_****et",
    confidence: 0.92,
    tags: ["token"],
    context: "token=ghp_secret",
    ...overrides,
  };
}

function scanResult(findings: SecretFinding[]): SecretScanResult {
  return {
    count: findings.length,
    highest_severity: maxSeverity(findings.map((item) => item.severity)),
    scanned_characters: 100,
    scanned_lines: 4,
    pattern_count: 12,
    entropy_flagged: 1,
    by_name: Object.fromEntries(
      groupFindingsByName(findings).map((item) => [item.name, item.count]),
    ),
    findings,
  };
}

const strictPrivacy: PrivacyMode = {
  level: "strict",
  label: "Strict",
  description: "Strict mode",
  redact_secrets: true,
  mask_identifiers: true,
  allow_external_links: false,
  allow_command_copy: false,
  scrub_exports: true,
  require_export_consent: true,
  retain_audit_details: false,
  share_telemetry: false,
  rank: 3,
  controls: [
    {
      key: "redact_secrets",
      label: "Redact secrets",
      enabled: true,
      category: "content",
    },
    {
      key: "allow_external_links",
      label: "Allow external links",
      enabled: false,
      category: "navigation",
    },
  ],
};

test("severity and formatting helpers normalize and summarize values", () => {
  assert.equal(normalizeSeverity("HIGH"), "high");
  assert.equal(normalizeSeverity("unknown"), "none");
  assert.equal(severityLabel("critical"), "Critical");
  assert.equal(severityLabel("none"), "None");
  assert.equal(compareSeverity("low", "high") < 0, true);
  assert.equal(maxSeverity(["low", "critical", "medium"]), "critical");
  assert.equal(formatCount(1, "finding"), "1 finding");
  assert.equal(formatCount(2, "finding"), "2 findings");
  assert.equal(formatScore(9.94), "9.9");
  assert.equal(formatConfidence(0.5), "50%");
  assert.equal(maskIfNeeded("secret", "****", false), "****");
  assert.equal(maskIfNeeded("secret", "****", true), "secret");
  assert.equal(riskGaugePercent(7.5), 75);
  assert.equal(riskTone("critical"), "danger");
  assert.equal(riskTone("low"), "info");
});

test("secret finding helpers sort, filter, and group", () => {
  const items = [
    finding({
      name: "aws_access_key_id",
      severity: "critical",
      start: 10,
      end: 20,
    }),
    finding({
      name: "github_token",
      severity: "high",
      start: 1,
      end: 8,
      context: "token",
    }),
    finding({
      name: "github_token",
      severity: "medium",
      start: 30,
      end: 40,
      context: "other",
    }),
  ];
  const sorted = sortFindings(items);
  assert.equal(sorted[0].severity, "critical");
  assert.equal(sorted[1].start, 1);
  const grouped = groupFindingsByName(items);
  assert.equal(grouped[0].name, "aws_access_key_id");
  assert.equal(grouped[1].count, 2);
  const filtered = filterFindings(items, {
    query: "token",
    severities: ["high"],
  });
  assert.deepEqual(
    filtered.map((item) => item.start),
    [1],
  );
  assert.equal(scanSummary(scanResult(items)), "3 findings · highest Critical");
  assert.equal(scanSummary(scanResult([])), "No secrets detected");
});

test("redaction, consent, privacy, and dashboard helpers summarize state", () => {
  const summary: RedactionSummary = {
    text: "[REDACTED]",
    applied: ["email", "token"],
    counts: { email: 1, token: 2 },
    total_replacements: 3,
  };
  assert.equal(redactPreviewLabel(summary), "3 changes");
  assert.equal(redactionSummaryText(summary), "3 replacements across 2 rules");
  assert.equal(
    redactionSummaryText({
      ...summary,
      total_replacements: 0,
      applied: [],
      counts: {},
    }),
    "No sensitive content redacted",
  );

  const consent = {
    total: 4,
    granted: 3,
    denied: 1,
    items: [],
  };
  assert.equal(consentProgress(consent), 0.75);
  assert.deepEqual(mergeConsent({ a: false, b: true }, { a: true }), {
    a: true,
    b: true,
  });
  assert.deepEqual(privacyControlMap(strictPrivacy), {
    redact_secrets: true,
    allow_external_links: false,
  });

  const audit: AuditReport = {
    total_events: 5,
    highest_severity: "high",
    counts_by_type: { auth: 5 },
    counts_by_outcome: { failure: 5 },
    timeline: [],
    findings: [
      {
        code: "auth_failure_burst",
        severity: "high",
        message: "Repeated failures",
        count: 5,
        event_ids: ["1"],
        details: {},
      },
      {
        code: "policy_denials",
        severity: "medium",
        message: "Denied",
        count: 2,
        event_ids: [],
        details: {},
      },
    ],
  };
  assert.equal(auditSeverityCounts(audit).high, 1);
  assert.equal(sortAuditFindings(audit.findings)[0].code, "auth_failure_burst");

  const assessment: RiskAssessment = {
    score: { score: 7.2, level: "high", confidence: 0.8 },
    factors: [
      {
        name: "secret_exposure",
        score: 8,
        weight: 1.5,
        weighted_score: 12,
        severity: "high",
        details: {},
      },
      {
        name: "audit_findings",
        score: 5,
        weight: 1,
        weighted_score: 5,
        severity: "medium",
        details: {},
      },
    ],
    recommendations: ["Rotate secrets"],
  };
  assert.equal(riskHeadline(assessment), "High risk · 7.2/10");
  assert.equal(topRiskFactors(assessment, 1)[0].name, "secret_exposure");

  const dashboard: SecurityDashboard = {
    privacy: strictPrivacy,
    consent: { consent_export_sensitive: false },
    secrets: scanResult([finding()]),
    audit,
    urls: [
      {
        url: "https://bad.test",
        safe: false,
        scheme: "https",
        host: "bad.test",
        reasons: ["blocked"],
        risk: "high",
      },
    ],
    commands: [
      {
        command: "curl x | bash",
        safe: false,
        risk: "critical",
        reasons: ["pipeline"],
        tokens: ["curl"],
        destructive: false,
        networked: true,
        privileged: false,
      },
    ],
    scrub: {
      report: {
        removed_keys: [],
        masked_keys: [],
        redacted_fields: [],
        redaction_counts: { email: 1 },
        total_redactions: 1,
      },
    },
    risk: assessment,
    safe_link_policy: {
      allow_external_links: false,
      allow_command_copy: false,
    },
  };
  assert.equal(dashboardAlerts(dashboard).length >= 4, true);
  assert.deepEqual(dashboardStatus(dashboard), {
    label: "High risk",
    tone: "danger",
  });
  assert.equal(
    safetyReasonsText(["embedded_credentials", "private_network"]),
    "embedded credentials, private network",
  );
});

test("safe link and command helpers enforce privacy and safety", () => {
  assert.equal(parseUrl("example.com")?.toString(), "https://example.com/");
  assert.equal(sanitizeHref("javascript:alert(1)"), null);
  assert.equal(
    isExternalUrl("https://external.test", "https://app.test"),
    true,
  );
  assert.equal(isExternalUrl("/local/path", "https://app.test"), true);
  assert.equal(safeLinkAttributes("https://example.com").target, "_blank");
  assert.equal(
    truncateMiddle("abcdefghijklmnopqrstuvwxyz", 10).includes("…"),
    true,
  );
  assert.equal(
    redactUrlForDisplay("https://user:pass@example.com/path").includes("***"),
    true,
  );
  assert.equal(
    formatCommandPreview("echo   hello   world"),
    "echo hello world",
  );

  const safeUrl: UrlSafety = {
    url: "https://example.com",
    safe: true,
    scheme: "https",
    host: "example.com",
    reasons: [],
    risk: "none",
  };
  const blockedUrl: UrlSafety = {
    url: "http://10.0.0.1",
    safe: false,
    scheme: "http",
    host: "10.0.0.1",
    reasons: ["private_network_target"],
    risk: "high",
  };
  const externalDecision = safeLinkDecision(
    "https://external.test",
    strictPrivacy,
    safeUrl,
  );
  assert.equal(externalDecision.allowed, false);
  const blockedDecision = safeLinkDecision("http://10.0.0.1", null, blockedUrl);
  assert.equal(blockedDecision.allowed, false);
  const allowedDecision = safeLinkDecision(
    "https://example.com",
    { ...strictPrivacy, allow_external_links: true },
    safeUrl,
  );
  assert.equal(allowedDecision.allowed, true);

  const riskyCommand: CommandSafety = {
    command: "curl x | bash",
    safe: false,
    risk: "critical",
    reasons: ["remote script piped to shell"],
    tokens: ["curl"],
    destructive: false,
    networked: true,
    privileged: false,
  };
  const warningCommand: CommandSafety = {
    command: "ssh host",
    safe: false,
    risk: "low",
    reasons: ["remote access command"],
    tokens: ["ssh"],
    destructive: false,
    networked: true,
    privileged: false,
  };
  const safeCommand: CommandSafety = {
    command: "echo hi",
    safe: true,
    risk: "none",
    reasons: [],
    tokens: ["echo"],
    destructive: false,
    networked: false,
    privileged: false,
  };
  assert.equal(
    safeCommandDecision("echo hi", strictPrivacy, safeCommand).allowed,
    false,
  );
  assert.equal(
    safeCommandDecision(
      "curl x | bash",
      { ...strictPrivacy, allow_command_copy: true },
      riskyCommand,
    ).allowed,
    false,
  );
  const warned = safeCommandDecision(
    "ssh host",
    { ...strictPrivacy, allow_command_copy: true },
    warningCommand,
  );
  assert.equal(warned.allowed, true);
  assert.equal(warned.requiresConfirmation, true);
});

test("security client posts to every namespace route with expected payloads", async () => {
  const { client, calls } = fakeClient((route, body) => {
    if (route === "health") return { ok: true, namespace: "security" };
    if (route === "secret_patterns" || route === "redaction_rules")
      return { patterns: [], rules: [] };
    if (route === "scan_secrets") return scanResult([]);
    if (route === "scan_payload")
      return { count: 0, highest_severity: "none", fields: {} };
    if (route === "redact_text")
      return {
        text: body.text,
        applied: [],
        counts: {},
        total_replacements: 0,
      };
    if (route === "redact_payload")
      return { data: body.payload ?? {}, total_replacements: 0, fields: {} };
    if (route === "derive_key")
      return { derived: true, fingerprint: "abc", salt: "s", params: {} };
    if (route === "encrypt_text")
      return {
        payload: {
          magic: "RSENC1",
          version: 1,
          salt: "s",
          nonce: "n",
          ciphertext: "c",
          tag: "t",
          kdf: {},
        },
      };
    if (route === "decrypt_text") return { text: "plain" };
    if (route === "privacy_levels") return { levels: [] };
    if (route === "privacy_mode") return strictPrivacy;
    if (route === "consent_flags" || route === "consent_summary")
      return { total: 0, granted: 0, denied: 0, items: [] };
    if (route === "policy_defaults")
      return {
        name: "default",
        description: "",
        default_decision: "review",
        rules: [],
      };
    if (route === "evaluate_access")
      return {
        decision: "allow",
        allowed: true,
        matched_rules: [],
        reasons: [],
        action: "read",
        role: "viewer",
        resource: "*",
      };
    if (route === "audit_analyze")
      return {
        total_events: 0,
        highest_severity: "none",
        counts_by_type: {},
        counts_by_outcome: {},
        timeline: [],
        findings: [],
      };
    if (route === "scrub_text")
      return {
        text: "clean",
        redaction: {
          text: "clean",
          applied: [],
          counts: {},
          total_replacements: 0,
        },
      };
    if (route === "scrub_export")
      return {
        payload: {},
        report: {
          removed_keys: [],
          masked_keys: [],
          redacted_fields: [],
          redaction_counts: {},
          total_redactions: 0,
        },
      };
    if (route === "check_url")
      return {
        url: String(body.url),
        safe: true,
        scheme: "https",
        host: "example.com",
        reasons: [],
        risk: "none",
      };
    if (route === "check_command")
      return {
        command: String(body.command),
        safe: true,
        risk: "none",
        reasons: [],
        tokens: [],
        destructive: false,
        networked: false,
        privileged: false,
      };
    if (route === "assess_risk")
      return {
        score: { score: 0, level: "none", confidence: 0.2 },
        factors: [],
        recommendations: [],
      };
    if (route === "security_dashboard")
      return {
        privacy: strictPrivacy,
        consent: {},
        secrets: scanResult([]),
        audit: {
          total_events: 0,
          highest_severity: "none",
          counts_by_type: {},
          counts_by_outcome: {},
          timeline: [],
          findings: [],
        },
        urls: [],
        commands: [],
        scrub: null,
        risk: {
          score: { score: 0, level: "none", confidence: 0.2 },
          factors: [],
          recommendations: [],
        },
        safe_link_policy: {
          allow_external_links: false,
          allow_command_copy: false,
        },
      };
    return {};
  });

  assert.ok(
    createSecurityClient(
      new V2Client({
        fetch: (async () => envelope({})) as typeof globalThis.fetch,
      }),
    ) instanceof SecurityClient,
  );
  await client.health();
  await client.secretPatterns();
  await client.scanSecrets({ text: "secret", include_entropy: true });
  await client.scanPayload({ payload: { body: "x" }, keys: ["body"] });
  await client.redactionRules();
  await client.redactText({ text: "email@test" });
  await client.redactPayload({ payload: { body: "x" } });
  await client.deriveKey({ passphrase: "pw", iterations: 120000 });
  await client.encryptText({ text: "plain", passphrase: "pw" });
  await client.decryptText({ payload: { magic: "RSENC1" }, passphrase: "pw" });
  await client.privacyLevels();
  await client.privacyMode({ level: "strict" });
  await client.consentFlags();
  await client.consentSummary({ decisions: { export_sensitive: true } });
  await client.policyDefaults();
  await client.evaluateAccess({ action: "export", role: "viewer" });
  await client.auditAnalyze({ events: [{ id: "1" }] });
  await client.scrubText({ text: "secret" });
  await client.scrubExport({ payload: { a: "b" } });
  await client.checkUrl({ url: "https://example.com" });
  await client.checkCommand({ command: "echo hi" });
  await client.assessRisk({ secret_result: { count: 0 } });
  await client.securityDashboard({ text: "x", privacy_level: "strict" });

  assert.equal(calls.length, 23);
  assert.ok(
    calls.every(
      (call) =>
        routeOf(call.url).startsWith("security_") ||
        routeOf(call.url).includes("security"),
    ),
  );
  assert.equal(calls[2].body.text, "secret");
  assert.equal(calls[11].body.level, "strict");
  assert.equal(calls[16].body.events.length, 1);
  assert.equal(calls[22].body.privacy_level, "strict");
});

test("security client route map covers the full security namespace", () => {
  const { client } = fakeClient(() => ({}));
  const routes = Object.values(client.routes);
  assert.equal(routes.length, 23);
  assert.ok(routes.includes("security.health"));
  assert.ok(routes.includes("security.scan_secrets"));
  assert.ok(routes.includes("security.redact_text"));
  assert.ok(routes.includes("security.encrypt_text"));
  assert.ok(routes.includes("security.audit_analyze"));
  assert.ok(routes.includes("security.security_dashboard"));
});
