/** Types for the in-app API explorer, manifest editor, and developer console. */

export type ContributionKind =
  | "panel"
  | "command"
  | "theme"
  | "shortcut"
  | "view";

export interface ExtensionContribution {
  kind: ContributionKind;
  id: string;
  title: string;
  location?: string;
  binding?: string;
  route?: string;
  group?: string;
  description?: string;
  tokens?: Record<string, string>;
}

export interface ExtensionManifest {
  schema: string;
  id: string;
  version: string;
  title: string;
  summary: string;
  requires: string[];
  contributions: ExtensionContribution[];
  metadata: Record<string, unknown>;
}

export interface ValidationIssue {
  path: string;
  code: string;
  message: string;
  severity: "error" | "warning";
}

export interface ValidationReport {
  valid: boolean;
  issues: ValidationIssue[];
  fingerprint: string;
  normalized?: ExtensionManifest | null;
}

export interface RouteInfoLite {
  path: string;
  methods: string[];
  public: boolean;
}

export interface ExplorerRequest {
  namespace: string;
  action: string;
  bodyText: string;
  capability: string;
  etag: string;
  idempotencyKey: string;
  allowWrite: boolean;
}

export interface ExplorerResponse {
  ok: boolean;
  status: number;
  requestId: string;
  etag: string;
  data: unknown;
  errorCode: string;
  errorMessage: string;
  warnings: string[];
}

export interface ConsoleEntry {
  id: string;
  sequence: number;
  route: string;
  status: number;
  requestId: string;
  etag: string;
  errorCode: string;
  durationMs: number;
  timestamp: number;
  cached: boolean;
  capability: string;
  bodyKeys: string[];
  responsePreview: string;
}

export interface CapabilityDecision {
  name: string;
  granted: boolean;
  reason: string;
  required_for: string;
  source: string;
}

export interface NegotiationResult {
  decisions: CapabilityDecision[];
  granted: boolean;
  denied: string[];
}

export interface ManifestSchemaInfo {
  schema_id: string;
  top_level: Record<string, string[]>;
  contribution_kinds: Record<string, Record<string, string[]>>;
  panel_locations: string[];
  forbidden_keys: string[];
  limits: Record<string, number>;
  data_only: boolean;
  executes_code: boolean;
}

export interface PageSummary {
  items: unknown[];
  total: number;
  hasNext: boolean;
  cursor: string;
}

export type ExplorerTab = "explorer" | "manifest" | "console";

export interface ParsedJson<T> {
  value: T | null;
  error: string;
  ok: boolean;
}
