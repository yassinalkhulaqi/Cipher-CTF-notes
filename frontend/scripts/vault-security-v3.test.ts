import assert from "node:assert/strict";
import test from "node:test";

import { V3Client, ApiClientError } from "../src/v3/apiClient";
import {
  VaultSecurityClient,
  createVaultSecurityClient,
} from "../src/features/vault-security/client";
import {
  CONSENT_SCOPES,
  auditCounts,
  canShowContent,
  checkPassphrase,
  consentLabel,
  effectiveRules,
  filterAudit,
  formatTimestamp,
  gapSummary,
  lockedMessage,
  maskRecoveryCode,
  needsSetup,
  needsUnlock,
  posturePercent,
  postureTone,
  printableCodes,
  recoveryWarning,
  redactionNotice,
  safeErrorText,
  severityTone,
  sortedChecks,
  wizardSteps,
} from "../src/features/vault-security/pure";
import type {
  AuditEntry,
  AuditList,
  PolicySnapshot,
  PostureCheck,
  PostureReport,
  VaultStatus,
} from "../src/features/vault-security/types";

function check(
  id: string,
  passed: boolean,
  severity: PostureCheck["severity"] = "medium",
): PostureCheck {
  return {
    id,
    label: id,
    passed,
    severity,
    detail: `detail for ${id}`,
    remediation: `fix ${id}`,
    weight: 10,
  };
}

function report(overrides: Partial<PostureReport> = {}): PostureReport {
  return {
    score: 72,
    level: "fair",
    passed: 3,
    total: 4,
    checks: [
      check("vault_encrypted", true, "critical"),
      check("audit_present", false, "low"),
    ],
    gap_ids: ["audit_present"],
    generated_at: 1700000000,
    warnings: [],
    contains_secrets: false,
    ...overrides,
  };
}

function status(state: VaultStatus["state"] = "locked"): VaultStatus {
  return {
    vault_id: "case-1",
    state,
    initialized: state !== "uninitialized",
    active_key_id: state === "uninitialized" ? "" : "key_001",
    key_version: state === "uninitialized" ? 0 : 1,
    rotation_count: 0,
    recovery_active: 3,
    audit_total: 2,
    posture: report(),
  };
}

function entry(index: number, overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    entry_id: `audit_${index}`,
    action: index % 2 === 0 ? "vault.setup" : "vault.unlock",
    outcome: index % 3 === 0 ? "denied" : "success",
    actor: index % 2 === 0 ? "local" : "operator@example.com",
    subject: "case-1",
    timestamp: 1700000000 + index,
    detail: { key_id: "key_001" },
    request_id: `req_${index}`,
    ...overrides,
  };
}

function envelope(data: unknown, statusCode = 200): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: { request_id: "req_test", api_version: "3.0" },
    }),
    { status: statusCode, headers: { "Content-Type": "application/json" } },
  );
}

function errorEnvelope(code: string, message: string): Response {
  return new Response(
    JSON.stringify({
      error: {
        code,
        message,
        field: "passphrase",
        retryable: false,
        context: {},
      },
      meta: { request_id: "req_test", api_version: "3.0" },
    }),
    { status: 403, headers: { "Content-Type": "application/json" } },
  );
}

interface Call {
  url: string;
  body: Record<string, unknown>;
}

function fakeClient(
  handler: (route: string, body: Record<string, unknown>) => unknown,
): { client: VaultSecurityClient; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    const url = String(input);
    const body = JSON.parse(String(init.body ?? "{}")) as Record<
      string,
      unknown
    >;
    calls.push({ url, body });
    const route = url.slice(url.lastIndexOf("/") + 1);
    const result = handler(route, body);
    return result instanceof Response ? result : envelope(result);
  }) as typeof globalThis.fetch;
  return {
    client: new VaultSecurityClient(
      new V3Client({ fetch: fetchImpl, requestId: () => "req_test" }),
    ),
    calls,
  };
}

test("posture tone, percent, and gap summary", () => {
  assert.equal(postureTone("strong"), "good");
  assert.equal(postureTone("fair"), "warn");
  assert.equal(postureTone("weak"), "bad");
  assert.equal(postureTone("critical"), "bad");
  assert.equal(posturePercent(72), 72);
  assert.equal(posturePercent(200), 100);
  assert.equal(posturePercent(-5), 0);
  assert.equal(posturePercent(Number.NaN), 0);
  assert.equal(gapSummary(report()), "1 gap to resolve");
  assert.equal(gapSummary(report({ gap_ids: [] })), "All security checks pass");
  assert.equal(
    gapSummary(report({ gap_ids: ["a", "b"] })),
    "2 gaps to resolve",
  );
});

test("checks sort failures and critical severity first", () => {
  const checks = [
    check("low_pass", true, "low"),
    check("critical_fail", false, "critical"),
    check("medium_fail", false, "medium"),
    check("critical_pass", true, "critical"),
  ];
  const sorted = sortedChecks(report({ checks }));
  assert.deepEqual(
    sorted.map((item) => item.id),
    ["critical_fail", "medium_fail", "critical_pass", "low_pass"],
  );
  assert.equal(severityTone("critical"), "bad");
  assert.equal(severityTone("high"), "bad");
  assert.equal(severityTone("medium"), "warn");
  assert.equal(severityTone("low"), "neutral");
});

test("recovery codes and passphrase checks never reveal secrets", () => {
  assert.equal(maskRecoveryCode("ABCDE-FGHJK-MNPQR"), "ABCDE-•••••-•••••");
  assert.equal(maskRecoveryCode(""), "[hidden]");
  assert.deepEqual(checkPassphrase("long enough phrase 2026"), {
    valid: true,
    reason: "Passphrase looks strong enough",
  });
  assert.equal(checkPassphrase("short").valid, false);
  assert.equal(checkPassphrase(" leading space phrase").valid, false);
  assert.equal(
    checkPassphrase("long enough phrase 2026", "different").valid,
    false,
  );
  assert.equal(safeErrorText("  "), "The request could not be completed");
  assert.equal(
    safeErrorText("Passphrase verification failed"),
    "Verification failed. Check your credentials and try again.",
  );
  assert.equal(safeErrorText("x".repeat(500)).length, 200);
});

test("wizard steps and locked states", () => {
  const fresh = wizardSteps("uninitialized", []);
  assert.deepEqual(
    fresh.map((step) => step.complete),
    [false, false, false],
  );
  const configured = wizardSteps("locked", ["ABCDE-FGHJK-MNPQR"]);
  assert.deepEqual(
    configured.map((step) => step.complete),
    [true, true, true],
  );
  assert.equal(needsSetup("uninitialized"), true);
  assert.equal(needsSetup("locked"), false);
  assert.equal(needsUnlock("locked"), true);
  assert.equal(needsUnlock("unlocked"), false);
  assert.equal(canShowContent("unlocked"), true);
  assert.equal(canShowContent("locked"), false);
  assert.match(lockedMessage("locked"), /unlock/i);
  assert.match(lockedMessage("uninitialized"), /not configured/i);
});

test("audit filtering, counts, and timestamps", () => {
  const entries = [entry(0), entry(1), entry(2)];
  const list: AuditList = {
    entries,
    total: 3,
    filter: {},
    stats: { total: 3, by_outcome: {}, by_action: {} },
  };
  assert.equal(
    filterAudit(entries, { action: "", outcome: "", actor: "", limit: 50 })
      .length,
    3,
  );
  assert.equal(
    filterAudit(entries, { action: "setup", outcome: "", actor: "", limit: 50 })
      .length,
    2,
  );
  assert.equal(
    filterAudit(entries, {
      action: "",
      outcome: "denied",
      actor: "",
      limit: 50,
    }).length,
    1,
  );
  assert.equal(
    filterAudit(entries, {
      action: "",
      outcome: "",
      actor: "operator",
      limit: 50,
    }).length,
    1,
  );
  assert.equal(
    filterAudit(entries, { action: "", outcome: "", actor: "", limit: 1 })
      .length,
    1,
  );
  assert.deepEqual(auditCounts(list), { success: 2, denied: 1, other: 0 });
  assert.equal(formatTimestamp(1700000000), "2023-11-14 22:13:20");
  assert.equal(formatTimestamp(0), "unknown");
});

test("policy display helpers", () => {
  const snapshot: PolicySnapshot = {
    patterns: [
      {
        name: "github_token",
        kind: "token",
        severity: "critical",
        description: "token",
        enabled: true,
        default_mode: "mask",
      },
      {
        name: "ctf_flag",
        kind: "flag",
        severity: "high",
        description: "flag",
        enabled: false,
        default_mode: "mask",
      },
    ],
    rules: [
      {
        rule_id: "low",
        pattern: "github_token",
        mode: "mask",
        priority: 1,
        enabled: true,
        reason: "",
      },
      {
        rule_id: "high",
        pattern: "*",
        mode: "remove",
        priority: 9,
        enabled: true,
        reason: "",
      },
      {
        rule_id: "off",
        pattern: "ctf_flag",
        mode: "hash",
        priority: 10,
        enabled: false,
        reason: "",
      },
      {
        rule_id: "missing",
        pattern: "not_real",
        mode: "mask",
        priority: 5,
        enabled: true,
        reason: "",
      },
    ],
    consents: { granted: ["export_plaintext"], pending: ["ai_assist"] },
    max_scan_chars: 200000,
  };
  const rules = effectiveRules(snapshot);
  assert.deepEqual(
    rules.map((rule) => rule.rule_id),
    ["high", "missing", "low"],
  );
  assert.equal(rules[1].effective, false);
  assert.equal(
    consentLabel(CONSENT_SCOPES[0], true),
    "Plaintext export: granted",
  );
  assert.equal(
    consentLabel(CONSENT_SCOPES[2], false),
    "AI assistance: not granted",
  );
  assert.match(redactionNotice(0), /No secrets/);
  assert.match(redactionNotice(2), /2 secret values/);
  assert.match(recoveryWarning(["a", "b"]), /Store 2 recovery codes/);
  assert.equal(printableCodes(["a", "b"]), "a\nb");
});

test("client calls the security namespace with typed envelopes", async () => {
  const { client, calls } = fakeClient((route) => {
    switch (route) {
      case "status":
        return status("unlocked");
      case "posture":
        return report();
      case "setup":
        return {
          vault_id: "case-1",
          key_id: "key_001",
          created_at: 1,
          recovery_codes: ["ABCDE-FGHJK-MNPQR"],
        };
      case "unlock":
        return {
          state: "unlocked",
          key_id: "key_001",
          version: 1,
          unlocked_at: 1,
        };
      case "lock":
        return { state: "locked", locked_at: 2 };
      case "rotate":
        return { from_key_id: "key_001", to_key_id: "key_002", to_version: 2 };
      case "recovery_issue":
        return { recovery_codes: ["ZZZZZ-YYYYY-XXXXX"] };
      case "recover":
        return { code_id: "rc_0001", key_id: "key_003", remaining_active: 1 };
      case "policy_get":
        return {
          patterns: [],
          rules: [],
          consents: { granted: [], pending: [] },
          max_scan_chars: 1,
        };
      case "policy_update":
        return {
          patterns: [],
          rules: [],
          consents: { granted: [], pending: [] },
          max_scan_chars: 1,
        };
      case "policy_preview":
        return {
          decision: { allowed: true },
          preview: { text: "[redacted]", redactions: 1 },
        };
      case "audit_list":
        return {
          entries: [entry(0)],
          total: 1,
          filter: {},
          stats: { total: 1, by_outcome: {}, by_action: {} },
        };
      case "audit_export":
        return { format: "json", document: "{}" };
      case "events":
        return { events: [{ kind: "vault.setup" }] };
      default:
        return {};
    }
  });
  assert.equal((await client.status()).vault_id, "case-1");
  assert.equal((await client.posture()).score, 72);
  const setup = await client.setup("passphrase not logged", {}, 2);
  assert.deepEqual(setup.recovery_codes, ["ABCDE-FGHJK-MNPQR"]);
  assert.equal(calls[2].body["recovery_count"], 2);
  assert.equal((await client.unlock("pass phrase value")).state, "unlocked");
  assert.equal((await client.lock()).state, "locked");
  assert.equal((await client.rotate("new long passphrase")).to_version, 2);
  assert.deepEqual(await client.issueRecoveryCodes("pass phrase value", 1), [
    "ZZZZZ-YYYYY-XXXXX",
  ]);
  assert.equal(
    (await client.recover("ABCDE-FGHJK-MNPQR", "new long passphrase")).code_id,
    "rc_0001",
  );
  assert.deepEqual(await client.policyGet(), {
    patterns: [],
    rules: [],
    consents: { granted: [], pending: [] },
    max_scan_chars: 1,
  });
  await client.policyUpdate([], ["export_plaintext"], ["ai_assist"]);
  assert.deepEqual(calls[9].body["grants"], ["export_plaintext"]);
  assert.equal(
    (await client.policyPreview("text", "log_content")).preview.redactions,
    1,
  );
  assert.equal((await client.auditList({ limit: 5 })).total, 1);
  assert.equal((await client.auditExport("jsonl")).format, "json");
  assert.equal((await client.events()).length, 1);
  for (const call of calls) {
    assert.match(call.url, /^\/api\/v3\/security\//);
    assert.ok(
      !("new_passphrase" in call.body) ||
        call.body["new_passphrase"] !== undefined,
    );
  }
});

test("client raises typed errors for rejected passphrases", async () => {
  const { client } = fakeClient((route) => {
    if (route === "unlock")
      return errorEnvelope("forbidden", "Passphrase verification failed");
    return status();
  });
  await assert.rejects(
    () => client.unlock("wrong passphrase value"),
    (error: unknown) => {
      assert.ok(error instanceof ApiClientError);
      assert.equal(error.code, "forbidden");
      assert.equal(error.status, 403);
      return true;
    },
  );
});

test("factory uses the V3 base path", async () => {
  const urls: string[] = [];
  const fetchImpl = (async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return envelope(status());
  }) as typeof globalThis.fetch;
  const client = createVaultSecurityClient({
    basePath: "/custom/v3/",
    fetch: fetchImpl,
  });
  await client.status();
  assert.deepEqual(urls, ["/custom/v3/security/status"]);
});
