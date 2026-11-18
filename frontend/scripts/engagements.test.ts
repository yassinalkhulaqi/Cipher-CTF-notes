import assert from "node:assert/strict";
import test from "node:test";
import { EngagementApi } from "../src/features/engagements/api";
import {
  ASSET_KINDS,
  CONFIDENCES,
  CRITICALITIES,
  FINDING_STATUSES,
  SCOPE_RULE_KINDS,
  SEVERITIES,
  canTransition,
  confidenceRank,
  coverageGaps,
  coverageProgress,
  coverageTone,
  criticalityRank,
  duplicateGroups,
  effectiveScore,
  engagementRisk,
  engagementTitle,
  evaluateScope,
  filterAssets,
  filterCredentials,
  filterEngagements,
  filterFindings,
  filterServices,
  filterTargets,
  formatScore,
  groupFindingsByTarget,
  humanize,
  isCountedFinding,
  isOpenFinding,
  matchScopeRule,
  parseCsvList,
  parseCvssVector,
  parseIds,
  riskBand,
  riskScore,
  scopeActionTone,
  scoreBand,
  serializeCsvList,
  sortedCoverage,
  severityFromVector,
  severityRank,
  severityTotals,
  severityTone,
  sortEngagements,
  sortFindings,
  sortTargets,
  statusTone,
  targetLabel,
  transitionLabel,
  validateFindingDraft,
} from "../src/features/engagements/logic";

function finding(overrides = {}) {
  return {
    id: 1,
    engagement_id: 1,
    target_id: 10,
    asset_id: 0,
    service_id: 0,
    title: "SQL injection",
    summary: "Login form injects SQL",
    severity: "high",
    confidence: "confirmed",
    cvss_vector: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    cvss_score: 9.8,
    cwe: "CWE-89",
    cwes: ["CWE-89"],
    cves: ["CVE-2024-0001"],
    status: "open",
    duplicate_of: 0,
    owner: "analyst",
    impact: "Database compromise",
    remediation: "Use parameterized queries",
    reproduction_steps: "Submit ' OR 1=1--",
    references: ["https://owasp.org"],
    tags: ["web", "sqli"],
    transitions: [],
    resolved_at: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    allowed_actions: ["verify", "close"],
    duplicate_candidates: [],
    ...overrides,
  };
}

function target(id, overrides = {}) {
  return {
    id,
    engagement_id: 1,
    value: `host-${id}.example.test`,
    name: `Host ${id}`,
    kind: "host",
    description: "",
    status: "discovered",
    scope_status: "pending",
    criticality: "medium",
    tags: [],
    notes: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function scopeRule(id, kind, value, action) {
  return {
    id,
    engagement_id: 1,
    kind,
    value,
    action,
    notes: "",
    created_at: "2026-01-01T00:00:00Z",
  };
}

test("enum option lists stay stable", () => {
  assert.deepEqual(SEVERITIES, ["info", "low", "medium", "high", "critical"]);
  assert.deepEqual(CONFIDENCES, ["low", "medium", "high", "confirmed"]);
  assert.deepEqual(FINDING_STATUSES, [
    "draft",
    "open",
    "verified",
    "accepted_risk",
    "duplicate",
    "remediated",
    "closed",
  ]);
  assert.deepEqual(SCOPE_RULE_KINDS, [
    "domain",
    "ip_address",
    "cidr",
    "url",
    "port",
    "keyword",
  ]);
  assert.equal(ASSET_KINDS.length, 9);
  assert.equal(CRITICALITIES.length, 5);
});

test("humanize and formatting helpers produce readable labels", () => {
  assert.equal(humanize("accepted_risk"), "Accepted risk");
  assert.equal(humanize("  cvss--score "), "Cvss score");
  assert.equal(transitionLabel("mark_duplicate"), "Mark duplicate");
  assert.equal(targetLabel(target(1)), "Host 1");
  assert.equal(
    engagementTitle({ id: 2, key: "ENG-2", name: "Assessment" }),
    "Assessment",
  );
  assert.equal(formatScore(9), "9");
  assert.equal(formatScore(9.83), "9.8");
  assert.equal(formatScore(Number.NaN), "0.0");
});

test("ranks and tones map every domain value", () => {
  assert.equal(severityRank("critical"), 4);
  assert.equal(severityRank("info"), 0);
  assert.equal(confidenceRank("confirmed"), 3);
  assert.equal(criticalityRank("critical"), 4);
  assert.equal(severityTone("critical"), "danger");
  assert.equal(statusTone("active"), "success");
  assert.equal(statusTone("unknown"), "neutral");
  assert.equal(scopeActionTone("exclude"), "danger");
  assert.equal(riskBand(70), "danger");
  assert.equal(engagementRisk({ risk_band: "medium" }), "warning");
  assert.equal(engagementRisk({ risk_band: "none" }), "success");
});

test("finding predicates distinguish counted, open, and duplicate rows", () => {
  assert.equal(isOpenFinding(finding()), true);
  assert.equal(isOpenFinding(finding({ status: "closed" })), false);
  assert.equal(isCountedFinding(finding()), true);
  assert.equal(isCountedFinding(finding({ status: "duplicate" })), false);
  assert.equal(
    effectiveScore(finding({ cvss_score: 0, severity: "critical" })),
    10,
  );
  assert.equal(canTransition(finding(), "verify"), true);
  assert.equal(canTransition(finding(), "archive"), false);
});

test("filterFindings supports query, facets, tags, and open-only", () => {
  const rows = [
    finding(),
    finding({
      id: 2,
      title: "XSS",
      severity: "medium",
      status: "closed",
      confidence: "medium",
      target_id: 11,
      tags: ["web"],
      cves: [],
    }),
    finding({
      id: 3,
      title: "Host header",
      severity: "high",
      target_id: 11,
      confidence: "high",
      status: "draft",
      summary: "vhost confusion",
      cwes: [],
      cves: [],
      tags: ["recon"],
    }),
  ];
  assert.deepEqual(
    filterFindings(rows, {}).map((item) => item.id),
    [1, 2, 3],
  );
  assert.deepEqual(
    filterFindings(rows, { severity: "high" }).map((item) => item.id),
    [1, 3],
  );
  assert.deepEqual(
    filterFindings(rows, { status: "closed" }).map((item) => item.id),
    [2],
  );
  assert.deepEqual(
    filterFindings(rows, { confidence: "confirmed" }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterFindings(rows, { targetId: 10 }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterFindings(rows, { tag: "WEB" }).map((item) => item.id),
    [1, 2],
  );
  assert.deepEqual(
    filterFindings(rows, { openOnly: true }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterFindings(rows, { query: "vhost" }).map((item) => item.id),
    [3],
  );
  assert.deepEqual(
    filterFindings(rows, { query: "CVE-2024" }).map((item) => item.id),
    [1],
  );
});

test("sortFindings orders by severity, recency, title, and confidence", () => {
  const rows = [
    finding({
      id: 1,
      severity: "low",
      confidence: "low",
      title: "Zebra",
      updated_at: "2026-01-01",
    }),
    finding({
      id: 2,
      severity: "critical",
      confidence: "confirmed",
      title: "Alpha",
      updated_at: "2026-01-03",
    }),
    finding({
      id: 3,
      severity: "medium",
      confidence: "high",
      title: "Beta",
      updated_at: "2026-01-02",
    }),
  ];
  assert.deepEqual(
    sortFindings(rows).map((item) => item.id),
    [2, 3, 1],
  );
  assert.deepEqual(
    sortFindings(rows, "recent").map((item) => item.id),
    [2, 3, 1],
  );
  assert.deepEqual(
    sortFindings(rows, "title").map((item) => item.id),
    [2, 3, 1],
  );
  assert.deepEqual(
    sortFindings(rows, "confidence").map((item) => item.id),
    [2, 3, 1],
  );
});

test("groupFindingsByTarget and severityTotals summarize data", () => {
  const rows = [
    finding({ id: 1, target_id: 10 }),
    finding({ id: 2, target_id: 10, severity: "low" }),
    finding({ id: 3, target_id: 0, severity: "critical" }),
  ];
  const groups = groupFindingsByTarget(rows, [target(10)]);
  assert.deepEqual(
    groups.map((group) => group.label),
    ["Host 10", "Unassigned"],
  );
  assert.deepEqual(
    groups[0].findings.map((item) => item.id),
    [1, 2],
  );

  const totals = severityTotals(rows);
  assert.equal(totals[0].severity, "info");
  assert.equal(totals[4].total, 1);
  assert.equal(totals[4].open, 1);
});

test("riskScore weights severity and confidence with diminishing returns", () => {
  const rows = [
    finding({
      id: 1,
      severity: "critical",
      confidence: "confirmed",
      cvss_score: 10,
    }),
    finding({ id: 2, severity: "low", confidence: "low", cvss_score: 0 }),
    finding({ id: 3, severity: "medium", confidence: "high", cvss_score: 5 }),
    finding({
      id: 4,
      status: "duplicate",
      severity: "critical",
      confidence: "confirmed",
    }),
  ];
  const score = riskScore(rows);
  assert.ok(score > 15 && score < 60);
  assert.equal(riskBand(score), "info");
  assert.equal(riskBand(40), "warning");
  assert.equal(riskScore([]), 0);
});

test("target filters and sorting work across scope and criticality", () => {
  const rows = [
    target(1, { criticality: "critical", scope_status: "in_scope" }),
    target(2, {
      name: "Alpha",
      criticality: "low",
      scope_status: "pending",
      tags: ["web"],
    }),
    target(3, { value: "db.internal", scope_status: "out_of_scope" }),
  ];
  assert.deepEqual(
    filterTargets(rows, { query: "alpha" }).map((item) => item.id),
    [2],
  );
  assert.deepEqual(
    filterTargets(rows, { scope: "pending" }).map((item) => item.id),
    [2],
  );
  assert.deepEqual(
    filterTargets(rows, { criticality: "critical" }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    sortTargets(rows, "criticality").map((item) => item.id),
    [1, 3, 2],
  );
  assert.deepEqual(
    sortTargets(rows, "scope").map((item) => item.id),
    [1, 3, 2],
  );
  assert.deepEqual(
    sortTargets(rows, "name").map((item) => item.id),
    [2, 1, 3],
  );
});

test("inventory filters handle target, port, status, and text criteria", () => {
  const assets = [
    {
      id: 1,
      target_id: 10,
      name: "web-01",
      identifier: "10.0.0.1",
      owner: "ops",
    },
    {
      id: 2,
      target_id: 11,
      name: "db-01",
      identifier: "10.0.0.2",
      owner: "dba",
    },
  ];
  assert.deepEqual(
    filterAssets(assets, 10, "").map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterAssets(assets, 0, "dba").map((item) => item.id),
    [2],
  );

  const services = [
    {
      id: 1,
      target_id: 10,
      asset_id: 1,
      port: 443,
      name: "https",
      protocol: "tcp",
      product: "nginx",
      version: "1.25",
    },
    {
      id: 2,
      target_id: 11,
      asset_id: 2,
      port: 3306,
      name: "mysql",
      protocol: "tcp",
      product: "mysql",
      version: "8",
    },
  ];
  assert.deepEqual(
    filterServices(services, { port: 443 }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterServices(services, { assetId: 2 }).map((item) => item.id),
    [2],
  );
  assert.deepEqual(
    filterServices(services, { query: "nginx 1.25" }).map((item) => item.id),
    [1],
  );

  const credentials = [
    {
      id: 1,
      target_id: 10,
      username: "admin",
      kind: "password",
      status: "valid",
      secret_ref: "vault://a",
    },
    {
      id: 2,
      target_id: 11,
      username: "svc",
      kind: "api_token",
      status: "revoked",
      secret_ref: "vault://b",
    },
  ];
  assert.deepEqual(
    filterCredentials(credentials, { status: "valid" }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterCredentials(credentials, { targetId: 11 }).map((item) => item.id),
    [2],
  );
  assert.deepEqual(
    filterCredentials(credentials, { query: "vault://a" }).map(
      (item) => item.id,
    ),
    [1],
  );
});

test("scope matching gives exclusions priority over inclusions", () => {
  const rules = [
    scopeRule(1, "domain", "example.test", "include"),
    scopeRule(2, "keyword", "admin", "exclude"),
    scopeRule(3, "port", "8080", "include"),
  ];
  assert.equal(matchScopeRule(rules[0], "www.example.test"), true);
  assert.equal(matchScopeRule(rules[2], "10.0.0.1:8080"), true);
  assert.equal(matchScopeRule(rules[2], "10.0.0.1:80"), false);
  assert.equal(evaluateScope(rules, "www.example.test").decision, "included");
  assert.equal(evaluateScope(rules, "admin.example.test").decision, "excluded");
  assert.equal(evaluateScope(rules, "unknown.test").decision, "unspecified");
});

test("coverage helpers surface the weakest targets and gap counts", () => {
  const coverage = {
    engagement_id: 1,
    score: 0.55,
    level: "partial",
    targets: [
      {
        target_id: 2,
        target_name: "B",
        score: 0.2,
        level: "partial",
        gaps: ["no-services"],
      },
      {
        target_id: 1,
        target_name: "A",
        score: 0.9,
        level: "good",
        gaps: ["no-evidence", "no-services"],
      },
    ],
    uncovered: [2],
    partial: [1],
    priority: [2],
    gaps: [],
    percent: 55,
    gap_summary: [],
    criticality_distribution: {},
    out_of_scope_count: 0,
  };
  assert.equal(coverageProgress(coverage), 55);
  assert.equal(coverageTone("complete"), "success");
  assert.equal(coverageTone("missing"), "danger");
  assert.deepEqual(
    sortedCoverage(coverage).map((item) => item.target_id),
    [2, 1],
  );
  assert.deepEqual(coverageGaps(coverage), [
    { gap: "no-services", count: 2 },
    { gap: "no-evidence", count: 1 },
  ]);
});

test("csv and id parsing dedupe while preserving order", () => {
  assert.deepEqual(parseCsvList(" web, WEB , sqle, , web"), ["web", "sqle"]);
  assert.equal(serializeCsvList(["web", "WEB", "sqle"]), "web, sqle");
  assert.deepEqual(parseIds("1, 2; 2 3 x -4"), [1, 2, 3]);
});

test("CVSS parsing validates base vectors and derives severity bands", () => {
  const vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H";
  const parsed = parseCvssVector(vector);
  assert.equal(parsed?.version, "3.1");
  assert.equal(parsed?.AV, "N");
  assert.equal(parseCvssVector("CVSS:2.0/AV:N"), null);
  assert.equal(parseCvssVector("CVSS:3.1/AV:N/AC:L"), null);
  assert.equal(scoreBand(9.1), "critical");
  assert.equal(scoreBand(7.2), "high");
  assert.equal(scoreBand(4.5), "medium");
  assert.equal(scoreBand(2), "low");
  assert.equal(scoreBand(0), "info");
  assert.equal(severityFromVector(vector), "critical");
});

test("finding draft validation blocks empty titles and bad vectors", () => {
  const base = {
    title: "Finding",
    severity: "high",
    confidence: "confirmed",
    cvss_vector: "",
    reproduction_steps: "steps",
    status: "open",
  };
  assert.deepEqual(validateFindingDraft(base), {});
  assert.equal(
    validateFindingDraft({ ...base, title: "  " }).title,
    "Title is required",
  );
  assert.equal(
    validateFindingDraft({ ...base, cvss_vector: "bad" }).cvss_vector,
    "Use a CVSS 3.x base vector",
  );
  assert.equal(
    validateFindingDraft({
      ...base,
      status: "verified",
      reproduction_steps: "",
    }).reproduction_steps,
    "Evidence is required for verified findings",
  );
});

test("duplicate grouping maps child findings to canonical records", () => {
  const rows = [
    finding({ id: 1 }),
    finding({ id: 2, duplicate_of: 1, title: "Duplicate one" }),
    finding({ id: 3, duplicate_of: 1, title: "Duplicate two" }),
    finding({ id: 4 }),
  ];
  const groups = duplicateGroups(rows);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].canonical.id, 1);
  assert.deepEqual(
    groups[0].duplicates.map((item) => item.id),
    [2, 3],
  );
});

test("engagement list filtering and sorting are deterministic", () => {
  const rows = [
    {
      id: 1,
      key: "A",
      name: "Zeta",
      client: "Acme",
      owner: "ann",
      tags: ["web"],
      status: "active",
      updated_at: "2026-01-01",
    },
    {
      id: 2,
      key: "B",
      name: "Alpha",
      client: "Globex",
      owner: "bob",
      tags: ["ctf"],
      status: "planning",
      updated_at: "2026-01-03",
    },
  ];
  assert.deepEqual(
    filterEngagements(rows, { query: "globex" }).map((item) => item.id),
    [2],
  );
  assert.deepEqual(
    filterEngagements(rows, { status: "active" }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    filterEngagements(rows, { tag: "WEB" }).map((item) => item.id),
    [1],
  );
  assert.deepEqual(
    sortEngagements(rows, "name").map((item) => item.id),
    [2, 1],
  );
  assert.deepEqual(
    sortEngagements(rows, "status").map((item) => item.id),
    [1, 2],
  );
  assert.deepEqual(
    sortEngagements(rows, "updated").map((item) => item.id),
    [2, 1],
  );
});

class FakeV2Client {
  calls = [];

  async call(route, body = {}, options = {}) {
    this.calls.push({ route, body, options });
    if (route.endsWith(".list") || route === "engagements.activity") {
      return {
        data: [{ id: 1 }],
        meta: { cursor: null, next: "n", total: 1, limit: 20, has_more: false },
      };
    }
    return { id: 42, route };
  }
}

test("EngagementApi builds typed routes and normalizes list envelopes", async () => {
  const fake = new FakeV2Client();
  const api = new EngagementApi({ client: fake });

  const engagements = await api.listEngagements({ limit: 20 });
  assert.deepEqual(engagements.items, [{ id: 1 }]);
  assert.deepEqual(engagements.page, {
    cursor: null,
    next: "n",
    total: 1,
    limit: 20,
    has_more: false,
  });
  assert.equal(fake.calls[0].options.raw, true);

  const created = await api.createFinding(7, { title: "Issue" });
  assert.deepEqual(created, { id: 42, route: "findings.create" });
  assert.equal(fake.calls[1].body.engagement_id, 7);
  assert.match(fake.calls[1].options.idempotencyKey, /^eng-findings-create-/);
  assert.match(fake.calls[1].options.requestId, /^eng_/);

  await api.transitionFinding(42, "verify", { note: "confirmed" });
  assert.equal(fake.calls[2].route, "findings.transition");
  assert.deepEqual(fake.calls[2].body, {
    id: 42,
    action: "verify",
    note: "confirmed",
  });
});

test("EngagementApi exposes every engagement namespace area", async () => {
  const fake = new FakeV2Client();
  const api = new EngagementApi({ client: fake });
  await Promise.all([
    api.dashboard(1),
    api.portfolio(),
    api.workflows(),
    api.options(),
    api.seedDemo(),
    api.listScopeRules(1),
    api.evaluateScope(1, "example.test"),
    api.coverage(1),
    api.listAssets(1),
    api.listServices(1),
    api.listCredentials(1),
    api.listFindings(1),
    api.rotateCredential(3, "vault://new"),
    api.markDuplicate(4, 2),
  ]);
  assert.deepEqual(
    fake.calls.map((call) => call.route).sort(),
    [
      "credentials.list",
      "credentials.rotate",
      "engagements.dashboard",
      "engagements.options",
      "engagements.portfolio",
      "engagements.seed_demo",
      "engagements.workflows",
      "findings.duplicate",
      "findings.list",
      "scope.evaluate",
      "scope.list",
      "assets.list",
      "services.list",
      "targets.coverage",
    ].sort(),
  );
});
