import type {
  Asset,
  AssetKind,
  AssetStatus,
  Confidence,
  CoverageReport,
  Credential,
  CredentialKind,
  CredentialStatus,
  Criticality,
  EngagementRollup,
  EngagementStatus,
  EngagementSummary,
  Finding,
  FindingStatus,
  ScopeAction,
  ScopeRule,
  ScopeRuleKind,
  ScopeStatus,
  Service,
  ServiceStatus,
  Severity,
  Target,
  TargetCoverage,
  TargetKind,
  TargetStatus,
  Tone,
} from "./types";

export const SEVERITIES: Severity[] = [
  "info",
  "low",
  "medium",
  "high",
  "critical",
];
export const CONFIDENCES: Confidence[] = ["low", "medium", "high", "confirmed"];
export const FINDING_STATUSES: FindingStatus[] = [
  "draft",
  "open",
  "verified",
  "accepted_risk",
  "duplicate",
  "remediated",
  "closed",
];
export const ENGAGEMENT_STATUSES: EngagementStatus[] = [
  "planning",
  "active",
  "paused",
  "reporting",
  "closed",
  "archived",
];
export const SCOPE_STATUSES: ScopeStatus[] = [
  "unspecified",
  "in_scope",
  "out_of_scope",
  "pending",
  "waived",
];
export const TARGET_STATUSES: TargetStatus[] = [
  "discovered",
  "confirmed",
  "tested",
  "excluded",
  "out_of_service",
];
export const CRITICALITIES: Criticality[] = [
  "informational",
  "low",
  "medium",
  "high",
  "critical",
];
export const TARGET_KIND_OPTIONS: Array<{ value: TargetKind; label: string }> =
  [
    { value: "domain", label: "Domain" },
    { value: "ip_address", label: "IP address" },
    { value: "cidr", label: "CIDR range" },
    { value: "url", label: "URL" },
    { value: "host", label: "Host" },
    { value: "application", label: "Application" },
    { value: "network", label: "Network" },
    { value: "cloud", label: "Cloud" },
  ];
export const SCOPE_RULE_KINDS: ScopeRuleKind[] = [
  "domain",
  "ip_address",
  "cidr",
  "url",
  "port",
  "keyword",
];
export const ASSET_KINDS: AssetKind[] = [
  "server",
  "workstation",
  "database",
  "device",
  "repository",
  "container",
  "cloud_resource",
  "identity",
  "unknown",
];
export const ASSET_STATUSES: AssetStatus[] = [
  "identified",
  "enumerated",
  "assessed",
  "remediated",
  "decommissioned",
];
export const SERVICE_STATUSES: ServiceStatus[] = [
  "suspected",
  "discovered",
  "verified",
  "tested",
  "closed",
];
export const CREDENTIAL_KINDS: CredentialKind[] = [
  "password",
  "api_token",
  "ssh_key",
  "certificate",
  "cookie",
  "hash",
];
export const CREDENTIAL_STATUSES: CredentialStatus[] = [
  "candidate",
  "valid",
  "invalid",
  "revoked",
  "rotated",
];

const SEVERITY_RANK: Record<Severity, number> = {
  info: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

const CONFIDENCE_RANK: Record<Confidence, number> = {
  low: 0,
  medium: 1,
  high: 2,
  confirmed: 3,
};

const CRITICALITY_RANK: Record<Criticality, number> = {
  informational: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

const SEVERITY_SCORE: Record<Severity, number> = {
  info: 0,
  low: 3.9,
  medium: 6.9,
  high: 8.9,
  critical: 10,
};

const SEVERITY_TONE: Record<Severity, Tone> = {
  info: "info",
  low: "neutral",
  medium: "warning",
  high: "danger",
  critical: "danger",
};

const STATUS_TONE: Record<string, Tone> = {
  planning: "info",
  active: "success",
  paused: "warning",
  reporting: "accent",
  closed: "neutral",
  archived: "neutral",
  draft: "neutral",
  open: "warning",
  verified: "success",
  accepted_risk: "info",
  duplicate: "neutral",
  remediated: "success",
  discovered: "info",
  confirmed: "success",
  tested: "accent",
  excluded: "danger",
  out_of_service: "neutral",
  in_scope: "success",
  out_of_scope: "danger",
  pending: "warning",
  waived: "neutral",
  candidate: "neutral",
  valid: "success",
  invalid: "danger",
  revoked: "danger",
  rotated: "info",
};

export function humanize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

export function severityRank(severity: Severity): number {
  return SEVERITY_RANK[severity] ?? -1;
}

export function confidenceRank(confidence: Confidence): number {
  return CONFIDENCE_RANK[confidence] ?? -1;
}

export function criticalityRank(criticality: Criticality): number {
  return CRITICALITY_RANK[criticality] ?? -1;
}

export function severityTone(severity: Severity): Tone {
  return SEVERITY_TONE[severity] ?? "neutral";
}

export function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral";
}

export function effectiveScore(finding: Finding): number {
  return finding.cvss_score > 0
    ? finding.cvss_score
    : (SEVERITY_SCORE[finding.severity] ?? 0);
}

export function compareSeverity(left: Severity, right: Severity): number {
  return severityRank(left) - severityRank(right);
}

export function isOpenFinding(finding: Finding): boolean {
  return ["open", "verified", "accepted_risk"].includes(finding.status);
}

export function isCountedFinding(finding: Finding): boolean {
  return finding.status !== "duplicate" && finding.status !== "closed";
}

export function filterFindings(
  findings: Finding[],
  filters: {
    query?: string;
    severity?: Severity | "";
    status?: FindingStatus | "";
    confidence?: Confidence | "";
    targetId?: number;
    tag?: string;
    openOnly?: boolean;
  },
): Finding[] {
  const query = filters.query?.trim().toLowerCase() ?? "";
  return findings.filter((finding) => {
    if (filters.severity && finding.severity !== filters.severity) return false;
    if (filters.status && finding.status !== filters.status) return false;
    if (filters.confidence && finding.confidence !== filters.confidence)
      return false;
    if (filters.targetId && finding.target_id !== filters.targetId)
      return false;
    if (
      filters.tag &&
      !finding.tags.some(
        (tag) => tag.toLowerCase() === filters.tag?.toLowerCase(),
      )
    ) {
      return false;
    }
    if (filters.openOnly && !isOpenFinding(finding)) return false;
    if (!query) return true;
    const haystack = [
      finding.title,
      finding.summary,
      finding.impact,
      finding.remediation,
      finding.cwe,
      ...finding.cves,
      ...finding.tags,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
}

export function sortFindings(
  findings: Finding[],
  mode: "severity" | "recent" | "title" | "confidence" = "severity",
): Finding[] {
  const copy = [...findings];
  if (mode === "recent") {
    return copy.sort((left, right) =>
      right.updated_at.localeCompare(left.updated_at),
    );
  }
  if (mode === "title") {
    return copy.sort((left, right) => left.title.localeCompare(right.title));
  }
  if (mode === "confidence") {
    return copy.sort(
      (left, right) =>
        confidenceRank(right.confidence) - confidenceRank(left.confidence) ||
        compareSeverity(right.severity, left.severity),
    );
  }
  return copy.sort(
    (left, right) =>
      compareSeverity(right.severity, left.severity) ||
      effectiveScore(right) - effectiveScore(left) ||
      left.id - right.id,
  );
}

export function groupFindingsByTarget(
  findings: Finding[],
  targets: Target[],
): Array<{
  targetId: number;
  label: string;
  findings: Finding[];
}> {
  const names = new Map(
    targets.map((target) => [target.id, target.name || target.value]),
  );
  const groups = new Map<number, Finding[]>();
  for (const finding of findings) {
    const id = finding.target_id || -1;
    const bucket = groups.get(id) ?? [];
    bucket.push(finding);
    groups.set(id, bucket);
  }
  return [...groups.entries()]
    .map(([targetId, items]) => ({
      targetId,
      label:
        targetId < 0
          ? "Unassigned"
          : (names.get(targetId) ?? `Target ${targetId}`),
      findings: sortFindings(items),
    }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function severityTotals(findings: Finding[]): Array<{
  severity: Severity;
  total: number;
  open: number;
}> {
  return SEVERITIES.map((severity) => {
    const matching = findings.filter(
      (finding) => finding.severity === severity,
    );
    return {
      severity,
      total: matching.length,
      open: matching.filter(isOpenFinding).length,
    };
  });
}

export function riskScore(findings: Finding[]): number {
  const weights: Record<Severity, number> = {
    info: 0,
    low: 1,
    medium: 3,
    high: 7,
    critical: 15,
  };
  const multipliers: Record<Confidence, number> = {
    low: 0.4,
    medium: 0.7,
    high: 0.9,
    confirmed: 1,
  };
  const values = findings
    .filter(isCountedFinding)
    .map(
      (finding) =>
        Math.max(weights[finding.severity], finding.cvss_score * 1.5) *
        multipliers[finding.confidence],
    )
    .sort((left, right) => right - left);
  const total = values.reduce(
    (sum, value, index) => sum + value / (1 + index * 0.25),
    0,
  );
  return Math.min(100, Math.max(0, total));
}

export function riskBand(score: number): Tone {
  if (score >= 60) return "danger";
  if (score >= 35) return "warning";
  if (score >= 15) return "info";
  return "success";
}

export function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "0.0";
  return score.toFixed(1).replace(/\.0$/, "");
}

export function filterTargets(
  targets: Target[],
  filters: {
    query?: string;
    scope?: ScopeStatus | "";
    criticality?: Criticality | "";
  },
): Target[] {
  const query = filters.query?.trim().toLowerCase() ?? "";
  return targets.filter((target) => {
    if (filters.scope && target.scope_status !== filters.scope) return false;
    if (filters.criticality && target.criticality !== filters.criticality)
      return false;
    if (!query) return true;
    return [target.value, target.name, target.description, ...target.tags]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

export function sortTargets(
  targets: Target[],
  mode: "name" | "criticality" | "scope" = "name",
): Target[] {
  const copy = [...targets];
  if (mode === "criticality") {
    return copy.sort(
      (left, right) =>
        criticalityRank(right.criticality) -
          criticalityRank(left.criticality) ||
        left.value.localeCompare(right.value),
    );
  }
  if (mode === "scope") {
    return copy.sort(
      (left, right) =>
        left.scope_status.localeCompare(right.scope_status) ||
        left.value.localeCompare(right.value),
    );
  }
  return copy.sort((left, right) =>
    (left.name || left.value).localeCompare(
      right.name || right.value,
      undefined,
      {
        sensitivity: "base",
      },
    ),
  );
}

export function filterAssets(
  assets: Asset[],
  targetId: number,
  query: string,
): Asset[] {
  const needle = query.trim().toLowerCase();
  return assets.filter(
    (asset) =>
      (!targetId || asset.target_id === targetId) &&
      (!needle ||
        [asset.name, asset.identifier, asset.owner]
          .join(" ")
          .toLowerCase()
          .includes(needle)),
  );
}

export function filterServices(
  services: Service[],
  filters: {
    targetId?: number;
    assetId?: number;
    port?: number;
    query?: string;
  },
): Service[] {
  const needle = filters.query?.trim().toLowerCase() ?? "";
  return services.filter((service) => {
    if (filters.targetId && service.target_id !== filters.targetId)
      return false;
    if (filters.assetId && service.asset_id !== filters.assetId) return false;
    if (filters.port && service.port !== filters.port) return false;
    if (!needle) return true;
    return [service.name, service.product, service.version, service.protocol]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });
}

export function filterCredentials(
  credentials: Credential[],
  filters: { targetId?: number; status?: string; query?: string },
): Credential[] {
  const needle = filters.query?.trim().toLowerCase() ?? "";
  return credentials.filter((credential) => {
    if (filters.targetId && credential.target_id !== filters.targetId)
      return false;
    if (filters.status && credential.status !== filters.status) return false;
    if (!needle) return true;
    return [credential.username, credential.kind, credential.secret_ref]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });
}

export function matchScopeRule(rule: ScopeRule, value: string): boolean {
  const needle = value.trim().toLowerCase();
  const expression = rule.value.trim().toLowerCase();
  if (!needle || !expression) return false;
  if (rule.kind === "port") {
    return (
      needle.split(":").includes(expression) ||
      needle.endsWith(`:${expression}`)
    );
  }
  return needle.includes(expression) || expression.includes(needle);
}

export function evaluateScope(
  rules: ScopeRule[],
  value: string,
): {
  decision: "included" | "excluded" | "unspecified";
  matched: ScopeRule[];
} {
  const matched = rules.filter((rule) => matchScopeRule(rule, value));
  if (matched.some((rule) => rule.action === "exclude")) {
    return { decision: "excluded", matched };
  }
  if (matched.some((rule) => rule.action === "include")) {
    return { decision: "included", matched };
  }
  return { decision: "unspecified", matched };
}

export function scopeActionTone(action: ScopeAction): Tone {
  return action === "exclude" ? "danger" : "success";
}

export function coverageTone(level: string): Tone {
  if (level === "complete") return "success";
  if (level === "good") return "info";
  if (level === "partial") return "warning";
  return "danger";
}

export function coverageProgress(coverage: CoverageReport): number {
  return Math.round(Math.min(100, Math.max(0, coverage.score * 100)));
}

export function sortedCoverage(coverage: CoverageReport): TargetCoverage[] {
  return [...coverage.targets].sort(
    (left, right) =>
      left.score - right.score || left.target_id - right.target_id,
  );
}

export function coverageGaps(
  coverage: CoverageReport,
): Array<{ gap: string; count: number }> {
  const counts = new Map<string, number>();
  for (const target of coverage.targets) {
    for (const gap of target.gaps) {
      counts.set(gap, (counts.get(gap) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([gap, count]) => ({ gap, count }))
    .sort(
      (left, right) =>
        right.count - left.count || left.gap.localeCompare(right.gap),
    );
}

export function parseCsvList(raw: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const piece of raw.split(",")) {
    const value = piece.trim();
    if (!value) continue;
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(value);
  }
  return result;
}

export function serializeCsvList(values: string[]): string {
  return parseCsvList(values.join(",")).join(", ");
}

export function parseIds(raw: string): number[] {
  const values = raw
    .split(/[\s,;]+/)
    .map((part) => Number.parseInt(part.trim(), 10))
    .filter((value) => Number.isInteger(value) && value > 0);
  return [...new Set(values)];
}

const CVSS_BASE_METRICS = ["AV", "AC", "PR", "UI", "S", "C", "I", "A"];

export function parseCvssVector(vector: string): Record<string, string> | null {
  const parts = vector.trim().split("/");
  if (parts.length !== 9 || !/^CVSS:3\.[01]$/.test(parts[0] ?? "")) return null;
  const metrics: Record<string, string> = { version: parts[0].slice(5) };
  for (const part of parts.slice(1)) {
    const [key, value] = part.split(":");
    if (!key || !value) return null;
    metrics[key] = value;
  }
  if (!CVSS_BASE_METRICS.every((key) => Boolean(metrics[key]))) return null;
  return metrics;
}

export function scoreBand(score: number): Severity {
  if (score >= 9) return "critical";
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  if (score > 0) return "low";
  return "info";
}

export function severityFromVector(vector: string): Severity | null {
  if (!parseCvssVector(vector)) return null;
  const match = vector.match(/C:(H|L|N)\/I:(H|L|N)\/A:(H|L|N)/);
  if (!match) return "low";
  const weights: Record<string, number> = { H: 0.56, L: 0.22, N: 0 };
  const impact =
    1 -
    (1 - weights[match[1]]) * (1 - weights[match[2]]) * (1 - weights[match[3]]);
  const score = impact >= 0 ? impact * 10 : 0;
  return scoreBand(Math.min(10, score));
}

export function validateFindingDraft(draft: {
  title: string;
  severity: Severity;
  confidence: Confidence;
  cvss_vector: string;
  reproduction_steps: string;
  status?: FindingStatus;
}): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.title.trim()) errors.title = "Title is required";
  if (!draft.severity) errors.severity = "Severity is required";
  if (!draft.confidence) errors.confidence = "Confidence is required";
  if (draft.cvss_vector.trim() && !parseCvssVector(draft.cvss_vector)) {
    errors.cvss_vector = "Use a CVSS 3.x base vector";
  }
  if (draft.status === "verified" && !draft.reproduction_steps.trim()) {
    errors.reproduction_steps = "Evidence is required for verified findings";
  }
  return errors;
}

export function transitionLabel(action: string): string {
  return humanize(action);
}

export function canTransition(finding: Finding, action: string): boolean {
  return (finding.allowed_actions ?? []).includes(action);
}

export function duplicateGroups(
  findings: Finding[],
): Array<{ canonical: Finding; duplicates: Finding[] }> {
  const byId = new Map(findings.map((finding) => [finding.id, finding]));
  const groups = new Map<number, Finding[]>();
  for (const finding of findings) {
    if (!finding.duplicate_of) continue;
    const bucket = groups.get(finding.duplicate_of) ?? [];
    bucket.push(finding);
    groups.set(finding.duplicate_of, bucket);
  }
  return [...groups.entries()]
    .map(([canonicalId, duplicates]) => {
      const canonical = byId.get(canonicalId);
      return canonical ? { canonical, duplicates } : null;
    })
    .filter(
      (group): group is { canonical: Finding; duplicates: Finding[] } =>
        group !== null,
    )
    .sort((left, right) => left.canonical.id - right.canonical.id);
}

export function engagementRisk(rollup: EngagementRollup): Tone {
  const tones: Record<string, Tone> = {
    critical: "danger",
    high: "danger",
    medium: "warning",
    low: "info",
    none: "success",
  };
  return tones[rollup.risk_band] ?? "neutral";
}

export function filterEngagements(
  engagements: EngagementSummary[],
  filters: { query?: string; status?: EngagementStatus | ""; tag?: string },
): EngagementSummary[] {
  const query = filters.query?.trim().toLowerCase() ?? "";
  return engagements.filter((engagement) => {
    if (filters.status && engagement.status !== filters.status) return false;
    if (
      filters.tag &&
      !engagement.tags.some(
        (tag) => tag.toLowerCase() === filters.tag?.toLowerCase(),
      )
    ) {
      return false;
    }
    if (!query) return true;
    return [
      engagement.name,
      engagement.client,
      engagement.key,
      engagement.owner,
    ]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

export function engagementTitle(engagement: EngagementSummary): string {
  return engagement.name || engagement.key || `Engagement ${engagement.id}`;
}

export function sortEngagements(
  engagements: EngagementSummary[],
  mode: "updated" | "name" | "status" = "updated",
): EngagementSummary[] {
  const copy = [...engagements];
  if (mode === "name")
    return copy.sort((left, right) =>
      engagementTitle(left).localeCompare(engagementTitle(right)),
    );
  if (mode === "status") {
    return copy.sort(
      (left, right) =>
        left.status.localeCompare(right.status) || left.id - right.id,
    );
  }
  return copy.sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at),
  );
}

export function targetLabel(target: Target): string {
  return target.name || target.value || `Target ${target.id}`;
}
