import type {
  FindingV4,
  LifecycleStateV4,
  RetestVerdictV4,
  ScoreV4,
  SeverityV4,
} from "./client";

export type MetricCode =
  | "AV"
  | "AC"
  | "AT"
  | "PR"
  | "UI"
  | "VC"
  | "VI"
  | "VA"
  | "SC"
  | "SI"
  | "SA"
  | "E"
  | "CR"
  | "IR"
  | "AR";

export interface MetricOption {
  code: string;
  label: string;
  weight: number;
}

export interface MetricDefinition {
  code: MetricCode;
  label: string;
  options: MetricOption[];
}

export type MetricValues = Record<MetricCode, string>;

export const METRIC_CODES: MetricCode[] = [
  "AV",
  "AC",
  "AT",
  "PR",
  "UI",
  "VC",
  "VI",
  "VA",
  "SC",
  "SI",
  "SA",
  "E",
  "CR",
  "IR",
  "AR",
];

const exploitabilityOptions = (
  values: Array<[string, string, number]>,
): MetricOption[] =>
  values.map(([code, label, weight]) => ({ code, label, weight }));

const impactOptions = (): MetricOption[] =>
  exploitabilityOptions([
    ["H", "High", 0.56],
    ["L", "Low", 0.22],
    ["N", "None", 0],
  ]);

const requirementOptions = (): MetricOption[] =>
  exploitabilityOptions([
    ["X", "Not defined", 1],
    ["H", "High", 1.5],
    ["M", "Medium", 1],
    ["L", "Low", 0.5],
  ]);

export const METRIC_DEFINITIONS: MetricDefinition[] = [
  {
    code: "AV",
    label: "Attack vector",
    options: exploitabilityOptions([
      ["N", "Network", 0.85],
      ["A", "Adjacent", 0.62],
      ["L", "Local", 0.55],
      ["P", "Physical", 0.2],
    ]),
  },
  {
    code: "AC",
    label: "Attack complexity",
    options: exploitabilityOptions([
      ["L", "Low", 0.77],
      ["H", "High", 0.44],
    ]),
  },
  {
    code: "AT",
    label: "Attack requirements",
    options: exploitabilityOptions([
      ["N", "None", 1],
      ["P", "Present", 0.9],
    ]),
  },
  {
    code: "PR",
    label: "Privileges required",
    options: exploitabilityOptions([
      ["N", "None", 0.85],
      ["L", "Low", 0.62],
      ["H", "High", 0.27],
    ]),
  },
  {
    code: "UI",
    label: "User interaction",
    options: exploitabilityOptions([
      ["N", "None", 0.85],
      ["P", "Passive", 0.62],
    ]),
  },
  ...(["VC", "VI", "VA"] as MetricCode[]).map((code) => ({
    code,
    label: `Vulnerable ${code.slice(1)}`,
    options: impactOptions(),
  })),
  ...(["SC", "SI", "SA"] as MetricCode[]).map((code) => ({
    code,
    label: `Subsequent ${code.slice(1)}`,
    options: impactOptions(),
  })),
  {
    code: "E",
    label: "Exploit maturity",
    options: exploitabilityOptions([
      ["X", "Not defined", 1],
      ["A", "Attacked", 1],
      ["P", "Proof of concept", 0.97],
      ["U", "Unreported", 0.6],
    ]),
  },
  ...(["CR", "IR", "AR"] as MetricCode[]).map((code) => ({
    code,
    label: `${code[0]} requirement`,
    options: requirementOptions(),
  })),
];

export const DEFAULT_METRICS: MetricValues = {
  AV: "N",
  AC: "L",
  AT: "N",
  PR: "N",
  UI: "N",
  VC: "N",
  VI: "N",
  VA: "N",
  SC: "N",
  SI: "N",
  SA: "N",
  E: "X",
  CR: "X",
  IR: "X",
  AR: "X",
};

const WEIGHTS: Record<MetricCode, Record<string, number>> = Object.fromEntries(
  METRIC_DEFINITIONS.map((definition) => [
    definition.code,
    Object.fromEntries(
      definition.options.map((option) => [option.code, option.weight]),
    ),
  ]),
) as Record<MetricCode, Record<string, number>>;

export function formatVector(metrics: MetricValues): string {
  return `CVSS:4.0/${METRIC_CODES.map((code) => `${code}:${metrics[code]}`).join("/")}`;
}

export function parseVectorText(text: string): MetricValues {
  const parts = text.trim().split("/");
  if (parts[0] !== "CVSS:4.0") {
    throw new Error("vector must start with CVSS:4.0");
  }
  const metrics: MetricValues = { ...DEFAULT_METRICS };
  const seen = new Set<MetricCode>();
  for (const part of parts.slice(1)) {
    const [code, value] = part.split(":");
    if (!METRIC_CODES.includes(code as MetricCode) || !value) {
      throw new Error(`invalid metric component: ${part}`);
    }
    if (seen.has(code as MetricCode)) {
      throw new Error(`duplicate metric: ${code}`);
    }
    seen.add(code as MetricCode);
    metrics[code as MetricCode] = value;
  }
  const missing = METRIC_CODES.slice(0, 11).filter((code) => !seen.has(code));
  if (missing.length > 0) {
    throw new Error(`missing base metrics: ${missing.join(", ")}`);
  }
  return metrics;
}

const weight = (code: MetricCode, value: string): number =>
  WEIGHTS[code][value] ?? 0;

export function estimateScore(metrics: MetricValues): number {
  const cr = weight("CR", metrics.CR);
  const ir = weight("IR", metrics.IR);
  const ar = weight("AR", metrics.AR);
  const c = Math.min(0.915, weight("VC", metrics.VC) * cr);
  const i = Math.min(0.915, weight("VI", metrics.VI) * ir);
  const a = Math.min(0.915, weight("VA", metrics.VA) * ar);
  const iscVuln = 1 - (1 - c) * (1 - i) * (1 - a);
  const iscSub =
    1 -
    (1 - weight("SC", metrics.SC)) *
      (1 - weight("SI", metrics.SI)) *
      (1 - weight("SA", metrics.SA));
  const impact =
    iscSub <= 0 ? 6.42 * iscVuln : 7.52 * (iscVuln + iscSub - iscVuln * iscSub);
  if (impact <= 0) return 0;
  const exploitability =
    8.22 *
    weight("AV", metrics.AV) *
    weight("AC", metrics.AC) *
    weight("AT", metrics.AT) *
    weight("PR", metrics.PR) *
    weight("UI", metrics.UI) *
    weight("E", metrics.E);
  return Math.min(10, Math.ceil((impact + exploitability) * 10 - 1e-9) / 10);
}

export function severityFromScore(score: number): SeverityV4 {
  if (score <= 0) return "none";
  if (score <= 3.9) return "low";
  if (score <= 6.9) return "medium";
  if (score <= 8.9) return "high";
  return "critical";
}

export function severityTone(severity: SeverityV4): string {
  switch (severity) {
    case "none":
      return "var(--v4-text-faint)";
    case "low":
      return "var(--v4-info)";
    case "medium":
      return "var(--v4-warning)";
    case "high":
      return "var(--v4-accent)";
    case "critical":
      return "var(--v4-danger)";
  }
}

export function scorePercent(score: number): number {
  return Math.max(0, Math.min(100, score * 10));
}

export const LIFECYCLE_STATES: LifecycleStateV4[] = [
  "draft",
  "open",
  "confirmed",
  "remediating",
  "retest",
  "closed",
  "accepted_risk",
];

export const LEGAL_TRANSITIONS_V4: Record<
  LifecycleStateV4,
  LifecycleStateV4[]
> = {
  draft: ["open"],
  open: ["confirmed", "closed", "accepted_risk"],
  confirmed: ["remediating", "accepted_risk"],
  remediating: ["retest", "open"],
  retest: ["closed", "remediating"],
  closed: ["open"],
  accepted_risk: ["open"],
};

export function legalTransitions(state: LifecycleStateV4): LifecycleStateV4[] {
  return LEGAL_TRANSITIONS_V4[state] ?? [];
}

export interface FindingStudioState {
  title: string;
  description: string;
  metrics: MetricValues;
  findings: FindingV4[];
  selectedId: string;
  score: ScoreV4 | null;
  remediationDue: string;
  remediationNotes: string;
  retestNote: string;
  verdict: RetestVerdictV4;
  log: string[];
  busy: boolean;
  error: string | null;
}

export type FindingStudioAction =
  | { type: "set-metric"; code: MetricCode; value: string }
  | { type: "set-title"; value: string }
  | { type: "set-description"; value: string }
  | { type: "set-score"; score: ScoreV4 | null }
  | { type: "load-findings"; findings: FindingV4[] }
  | { type: "select"; id: string }
  | { type: "apply-finding"; finding: FindingV4 }
  | { type: "set-due"; value: string }
  | { type: "set-notes"; value: string }
  | { type: "set-retest-note"; value: string }
  | { type: "set-verdict"; value: RetestVerdictV4 }
  | { type: "set-busy"; value: boolean }
  | { type: "set-error"; value: string | null }
  | { type: "log"; message: string }
  | { type: "reset" };

export function initialFindingStudioState(): FindingStudioState {
  return {
    title: "",
    description: "",
    metrics: { ...DEFAULT_METRICS },
    findings: [],
    selectedId: "",
    score: null,
    remediationDue: "",
    remediationNotes: "",
    retestNote: "",
    verdict: "fail",
    log: [],
    busy: false,
    error: null,
  };
}

export function selectedFinding(state: FindingStudioState): FindingV4 | null {
  return (
    state.findings.find((finding) => finding.id === state.selectedId) ?? null
  );
}

export function reduceFindingStudio(
  state: FindingStudioState,
  action: FindingStudioAction,
): FindingStudioState {
  switch (action.type) {
    case "set-metric":
      return {
        ...state,
        metrics: { ...state.metrics, [action.code]: action.value },
        score: null,
      };
    case "set-title":
      return { ...state, title: action.value };
    case "set-description":
      return { ...state, description: action.value };
    case "set-score":
      return { ...state, score: action.score };
    case "load-findings":
      return {
        ...state,
        findings: action.findings,
        selectedId: state.selectedId || action.findings[0]?.id || "",
      };
    case "select": {
      const finding = state.findings.find((item) => item.id === action.id);
      if (!finding) return state;
      return {
        ...state,
        selectedId: finding.id,
        title: finding.title,
        description: finding.description,
        remediationDue: finding.remediation_due ?? "",
        remediationNotes: finding.remediation_notes,
      };
    }
    case "apply-finding": {
      const findings = state.findings.map((finding) =>
        finding.id === action.finding.id ? action.finding : finding,
      );
      const exists = findings.some(
        (finding) => finding.id === action.finding.id,
      );
      return {
        ...state,
        findings: exists ? findings : [...findings, action.finding],
        selectedId: action.finding.id,
      };
    }
    case "set-due":
      return { ...state, remediationDue: action.value };
    case "set-notes":
      return { ...state, remediationNotes: action.value };
    case "set-retest-note":
      return { ...state, retestNote: action.value };
    case "set-verdict":
      return { ...state, verdict: action.value };
    case "set-busy":
      return { ...state, busy: action.value };
    case "set-error":
      return { ...state, error: action.value };
    case "log":
      return { ...state, log: [...state.log.slice(-19), action.message] };
    case "reset":
      return initialFindingStudioState();
    default:
      return state;
  }
}
