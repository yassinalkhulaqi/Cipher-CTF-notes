import type {
  ReportFormat,
  ReportPreview,
  RenderedReport,
  ReportingRequest,
  ValidationReport,
  RedactionResult,
} from "./types";

export type BuilderTextField =
  | "title"
  | "template"
  | "client"
  | "author"
  | "classification"
  | "minimumSeverity"
  | "pageSize"
  | "orientation"
  | "profile"
  | "generatedAt"
  | "notes"
  | "redactionText";

export type BuilderToggleField =
  | "includeEvidence"
  | "includeAppendices"
  | "redactSensitive";

export type BuilderListField = "scope" | "tags" | "statuses";

export interface BuilderState {
  title: string;
  template: string;
  client: string;
  author: string;
  classification: string;
  scope: string[];
  tags: string[];
  statuses: string[];
  minimumSeverity: string;
  pageSize: string;
  orientation: string;
  profile: string;
  format: ReportFormat;
  generatedAt: string;
  notes: string;
  includeEvidence: boolean;
  includeAppendices: boolean;
  redactSensitive: boolean;
  redactionText: string;
  preview: ReportPreview | null;
  validation: ValidationReport | null;
  rendered: RenderedReport | null;
  redaction: RedactionResult | null;
  busy: boolean;
  error: string;
}

export type BuilderAction =
  | { type: "field"; field: BuilderTextField; value: string }
  | { type: "toggle"; field: BuilderToggleField; value: boolean }
  | { type: "list"; field: BuilderListField; value: string[] }
  | { type: "format"; value: ReportFormat }
  | { type: "preview"; value: ReportPreview }
  | { type: "validation"; value: ValidationReport }
  | { type: "rendered"; value: RenderedReport }
  | { type: "redaction"; value: RedactionResult }
  | { type: "busy"; value: boolean }
  | { type: "error"; value: string }
  | { type: "reset" };

export const REPORT_FORMATS: readonly ReportFormat[] = [
  "markdown",
  "html",
  "json",
  "print",
];

export const BUILDER_DEFAULTS: BuilderState = {
  title: "Engagement Report",
  template: "engagement",
  client: "",
  author: "",
  classification: "internal",
  scope: [],
  tags: [],
  statuses: [],
  minimumSeverity: "info",
  pageSize: "a4",
  orientation: "portrait",
  profile: "standard",
  format: "html",
  generatedAt: "",
  notes: "",
  includeEvidence: true,
  includeAppendices: true,
  redactSensitive: true,
  redactionText: "",
  preview: null,
  validation: null,
  rendered: null,
  redaction: null,
  busy: false,
  error: "",
};

export function initialBuilderState(
  overrides: Partial<BuilderState> = {},
): BuilderState {
  return { ...BUILDER_DEFAULTS, ...overrides };
}

export function builderReducer(
  state: BuilderState,
  action: BuilderAction,
): BuilderState {
  switch (action.type) {
    case "field":
      return { ...state, [action.field]: action.value, error: "" };
    case "toggle":
      return { ...state, [action.field]: action.value };
    case "list":
      return { ...state, [action.field]: action.value };
    case "format":
      return { ...state, format: action.value, rendered: null };
    case "preview":
      return { ...state, preview: action.value };
    case "validation":
      return { ...state, validation: action.value };
    case "rendered":
      return { ...state, rendered: action.value, busy: false, error: "" };
    case "redaction":
      return { ...state, redaction: action.value };
    case "busy":
      return { ...state, busy: action.value };
    case "error":
      return { ...state, error: action.value, busy: false };
    case "reset":
      return { ...BUILDER_DEFAULTS };
    default:
      return state;
  }
}

export function splitList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function configFromState(state: BuilderState): ReportingRequest {
  return {
    title: state.title,
    template: state.template,
    client: state.client,
    author: state.author,
    classification: state.classification,
    scope: state.scope,
    tags: state.tags,
    statuses: state.statuses,
    minimum_severity: state.minimumSeverity,
    page_size: state.pageSize,
    orientation: state.orientation,
    print_profile: state.profile,
    include_evidence: state.includeEvidence,
    include_appendices: state.includeAppendices,
    redact_sensitive: state.redactSensitive,
    notes: state.notes,
    generated_at: state.generatedAt,
  };
}

export function previewSignature(state: BuilderState): string {
  return JSON.stringify([
    state.title,
    state.template,
    state.client,
    state.author,
    state.classification,
    state.scope,
    state.tags,
    state.statuses,
    state.minimumSeverity,
    state.pageSize,
    state.orientation,
    state.profile,
    state.includeEvidence,
    state.includeAppendices,
    state.redactSensitive,
    state.generatedAt,
  ]);
}
