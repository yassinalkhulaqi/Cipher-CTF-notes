/** Pure logic for the finding studio: vectors, filters, and lifecycle guides. */

import type {
  FindingState,
  FindingWire,
  ProofBlockWire,
  RemediationTaskWire,
  RetestVerdictValue,
  SeverityBand,
  TaskStatusValue,
} from "./types";

export interface MetricOption {
  code: string;
  label: string;
  values: Array<{ code: string; label: string }>;
}

const valueList = (...pairs: Array<[string, string]>) =>
  pairs.map(([code, label]) => ({ code, label }));

export const CVSS_METRICS: MetricOption[] = [
  {
    code: "AV",
    label: "Attack Vector",
    values: valueList(["N", "Network"], ["A", "Adjacent"], ["L", "Local"], ["P", "Physical"]),
  },
  {
    code: "AC",
    label: "Attack Complexity",
    values: valueList(["L", "Low"], ["H", "High"]),
  },
  {
    code: "AT",
    label: "Attack Requirements",
    values: valueList(["N", "None"], ["P", "Present"]),
  },
  {
    code: "PR",
    label: "Privileges Required",
    values: valueList(["N", "None"], ["L", "Low"], ["H", "High"]),
  },
  {
    code: "UI",
    label: "User Interaction",
    values: valueList(["N", "None"], ["P", "Passive"], ["A", "Active"]),
  },
  {
    code: "VC",
    label: "Vulnerable Confidentiality",
    values: valueList(["H", "High"], ["L", "Low"], ["N", "None"]),
  },
  {
    code: "VI",
    label: "Vulnerable Integrity",
    values: valueList(["H", "High"], ["L", "Low"], ["N", "None"]),
  },
  {
    code: "VA",
    label: "Vulnerable Availability",
    values: valueList(["H", "High"], ["L", "Low"], ["N", "None"]),
  },
  {
    code: "SC",
    label: "Subsequent Confidentiality",
    values: valueList(["H", "High"], ["L", "Low"], ["N", "None"]),
  },
  {
    code: "SI",
    label: "Subsequent Integrity",
    values: valueList(["H", "High"], ["L", "Low"], ["N", "None"]),
  },
  {
    code: "SA",
    label: "Subsequent Availability",
    values: valueList(["H", "High"], ["L", "Low"], ["N", "None"]),
  },
];

export const BASE_METRIC_CODES = CVSS_METRICS.map((metric) => metric.code);

export const THREAT_METRIC: MetricOption = {
  code: "E",
  label: "Exploit Maturity",
  values: valueList(
    ["X", "Not defined"],
    ["A", "Attacked"],
    ["P", "Proof of concept"],
    ["U", "Unreported"],
  ),
};

export const ENVIRONMENTAL_METRICS: MetricOption[] = [
  {
    code: "CR",
    label: "Confidentiality Requirement",
    values: valueList(["X", "Not defined"], ["H", "High"], ["M", "Medium"], ["L", "Low"]),
  },
  {
    code: "IR",
    label: "Integrity Requirement",
    values: valueList(["X", "Not defined"], ["H", "High"], ["M", "Medium"], ["L", "Low"]),
  },
  {
    code: "AR",
    label: "Availability Requirement",
    values: valueList(["X", "Not defined"], ["H", "High"], ["M", "Medium"], ["L", "Low"]),
  },
];

export const SEVERITY_BANDS: SeverityBand[] = ["none", "low", "medium", "high", "critical"];

export const FINDING_STATES: FindingState[] = [
  "draft",
  "confirmed",
  "remediated",
  "retested",
  "closed",
];

export const TASK_STATUSES: TaskStatusValue[] = ["todo", "in_progress", "done", "skipped"];

export const RETEST_VERDICTS: RetestVerdictValue[] = ["pass", "fail", "partial"];

export const SEVERITY_RANK: Record<SeverityBand, number> = {
  none: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

export type Tone = "neutral" | "good" | "warn" | "bad";

export function severityTone(band: SeverityBand): Tone {
  switch (band) {
    case "critical":
      return "bad";
    case "high":
      return "bad";
    case "medium":
      return "warn";
    case "low":
      return "good";
    default:
      return "neutral";
  }
}

export function scoreBand(score: number): SeverityBand {
  if (score <= 0) return "none";
  if (score < 4) return "low";
  if (score < 7) return "medium";
  if (score < 9) return "high";
  return "critical";
}

export function formatScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(1) : "0.0";
}

export class VectorParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VectorParseError";
  }
}

const METRIC_VALUE_SETS: Record<string, string[]> = {};
for (const metric of [...CVSS_METRICS, THREAT_METRIC, ...ENVIRONMENTAL_METRICS]) {
  METRIC_VALUE_SETS[metric.code] = metric.values.map((value) => value.code);
}
for (const modified of ["MAV", "MAC", "MAT", "MPR", "MUI", "MVC", "MVI", "MVA", "MSC"]) {
  const base = modified.slice(1);
  METRIC_VALUE_SETS[modified] = ["X", ...(METRIC_VALUE_SETS[base] ?? [])];
}
METRIC_VALUE_SETS.MSI = ["X", "H", "L", "N", "S"];
METRIC_VALUE_SETS.MSA = ["X", "H", "L", "N", "S"];

export function parseVector(vector: string): Record<string, string> {
  const parts = vector.trim().split("/");
  if (parts[0] !== "CVSS:4.0") throw new VectorParseError("Vector must start with CVSS:4.0");
  const metrics: Record<string, string> = {};
  for (const part of parts.slice(1)) {
    const [name, value] = part.split(":");
    if (!name || !value || value.includes(":")) throw new VectorParseError(`Invalid metric: ${part}`);
    if (name in metrics) throw new VectorParseError(`Duplicate metric: ${name}`);
    const allowed = METRIC_VALUE_SETS[name];
    if (!allowed) throw new VectorParseError(`Unknown metric: ${name}`);
    if (!allowed.includes(value)) throw new VectorParseError(`Invalid value for ${name}: ${value}`);
    metrics[name] = value;
  }
  return metrics;
}

export function buildVector(metrics: Record<string, string>): string {
  const ordered = [...BASE_METRIC_CODES, "E", ...ENVIRONMENTAL_METRICS.map((m) => m.code)];
  const parts = ["CVSS:4.0"];
  for (const code of ordered) {
    const value = metrics[code];
    if (value) parts.push(`${code}:${value}`);
  }
  for (const code of Object.keys(metrics).sort()) {
    if (!ordered.includes(code) && metrics[code]) parts.push(`${code}:${metrics[code]}`);
  }
  return parts.join("/");
}

export function setMetric(vector: string, name: string, value: string): string {
  const metrics = parseVector(vector);
  metrics[name] = value;
  return buildVector(metrics);
}

export function missingBaseMetrics(vector: string): string[] {
  let metrics: Record<string, string>;
  try {
    metrics = parseVector(vector);
  } catch {
    return [...BASE_METRIC_CODES];
  }
  return BASE_METRIC_CODES.filter((code) => !metrics[code]);
}

export function isCompleteVector(vector: string): boolean {
  return missingBaseMetrics(vector).length === 0;
}

export function metricLabel(code: string): string {
  const metric = [...CVSS_METRICS, THREAT_METRIC, ...ENVIRONMENTAL_METRICS].find(
    (item) => item.code === code,
  );
  return metric ? metric.label : code;
}

export interface FindingFilter {
  query?: string;
  state?: FindingState | "";
  severity?: SeverityBand | "";
  tag?: string;
  owner?: string;
}

export function filterFindings(findings: FindingWire[], filter: FindingFilter): FindingWire[] {
  const needle = (filter.query ?? "").trim().toLowerCase();
  return findings.filter((finding) => {
    if (filter.state && finding.state !== filter.state) return false;
    if (filter.severity && finding.severity !== filter.severity) return false;
    if (filter.tag && !finding.tags.some((tag) => tag.toLowerCase() === filter.tag?.toLowerCase())) {
      return false;
    }
    if (filter.owner && !finding.owner.toLowerCase().includes(filter.owner.toLowerCase())) {
      return false;
    }
    if (!needle) return true;
    const haystack = [
      finding.title,
      finding.summary,
      finding.owner,
      finding.ref,
      ...finding.tags,
      ...finding.mappings.cwes,
      ...finding.mappings.cves,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

export type SortKey = "score" | "title" | "updated" | "state";

export function sortFindings(findings: FindingWire[], key: SortKey): FindingWire[] {
  const copy = [...findings];
  return copy.sort((left, right) => {
    if (key === "score") return right.score - left.score || left.title.localeCompare(right.title);
    if (key === "title") return left.title.localeCompare(right.title);
    if (key === "updated") return right.updated_at - left.updated_at;
    return FINDING_STATES.indexOf(left.state) - FINDING_STATES.indexOf(right.state);
  });
}

export interface TransitionGuide {
  checklistComplete: boolean;
  lastVerdict?: RetestVerdictValue;
}

export function canTransition(
  finding: FindingWire,
  action: string,
  guide: TransitionGuide,
): boolean {
  const lastVerdict = guide.lastVerdict ?? finding.retests[finding.retests.length - 1]?.verdict;
  switch (action) {
    case "confirm":
      return finding.state === "draft";
    case "remediate":
      return finding.state === "confirmed" && guide.checklistComplete;
    case "retest":
      return finding.state === "remediated" && lastVerdict !== "partial";
    case "pass":
      return finding.state === "retested" && lastVerdict === "pass";
    case "fail":
      return finding.state === "retested" && lastVerdict === "fail";
    case "dismiss":
    case "reopen":
    case "regress":
      return (
        (action === "dismiss" && finding.state === "confirmed") ||
        (action === "reopen" && finding.state === "closed") ||
        (action === "regress" &&
          (finding.state === "remediated" || finding.state === "retested"))
      );
    default:
      return false;
  }
}

export function remediationPercent(tasks: RemediationTaskWire[]): number {
  if (tasks.length === 0) return 0;
  const settled = tasks.filter((task) => task.status === "done" || task.status === "skipped");
  return Math.round((settled.length / tasks.length) * 100);
}

export function nextTask(tasks: RemediationTaskWire[]): RemediationTaskWire | null {
  return tasks.find((task) => task.status !== "done" && task.status !== "skipped") ?? null;
}

export function proofIssueCount(blocks: ProofBlockWire[]): number {
  const badHashes = blocks.filter((block) => !block.verified).length;
  const empty = blocks.filter((block) => !block.excerpt).length;
  const ids = new Set(blocks.map((block) => block.block_id));
  return badHashes + empty + (blocks.length - ids.size);
}

export function shortRef(ref: string): string {
  return ref.startsWith("finding:") ? ref.slice("finding:".length) : ref;
}

export function duplicateConfidence(score: number): Tone {
  if (score >= 0.85) return "bad";
  if (score >= 0.65) return "warn";
  return "neutral";
}

export const EDITOR_SECTIONS = ["details", "cvss", "remediation", "retest", "duplicates"] as const;

export type EditorSection = (typeof EDITOR_SECTIONS)[number];

export function nextSection(current: EditorSection, direction: -1 | 1): EditorSection {
  const index = EDITOR_SECTIONS.indexOf(current);
  const next = Math.min(EDITOR_SECTIONS.length - 1, Math.max(0, index + direction));
  return EDITOR_SECTIONS[next];
}

export function taskSummary(tasks: RemediationTaskWire[]): string {
  if (tasks.length === 0) return "No remediation plan";
  const upcoming = nextTask(tasks);
  return upcoming ? `Next: ${upcoming.title}` : "Checklist complete";
}

export function elapsedLabel(timestamp: number, now: number): string {
  const seconds = Math.max(0, Math.floor(now - timestamp));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
