/** Pure validation, formatting, and safety helpers for the API explorer. */

import type {
  CapabilityDecision,
  ConsoleEntry,
  ContributionKind,
  ExplorerRequest,
  ExplorerResponse,
  ExtensionManifest,
  ParsedJson,
  ValidationIssue,
  ValidationReport,
} from "./types";

export const MANIFEST_SCHEMA_ID = "redscribe-extension/1";
export const MAX_CONTRIBUTIONS = 32;
export const MAX_HISTORY = 200;
export const CONTRIBUTION_KINDS: ContributionKind[] = [
  "panel",
  "command",
  "theme",
  "shortcut",
  "view",
];

export const FORBIDDEN_KEYS: string[] = [
  "args",
  "argv",
  "binary",
  "bytes",
  "call",
  "callable",
  "callback",
  "class",
  "code",
  "command",
  "compile",
  "entrypoint",
  "eval",
  "evaluate",
  "exec",
  "filepath",
  "filename",
  "function",
  "handler",
  "hook",
  "host",
  "import",
  "instance",
  "lambda",
  "module",
  "network",
  "on_load",
  "path",
  "port",
  "script",
  "shell",
  "socket",
  "source",
  "source_code",
  "subprocess",
  "uri",
  "url",
];

const TOP_LEVEL_FIELDS = [
  "schema",
  "id",
  "version",
  "title",
  "summary",
  "requires",
  "contributions",
  "metadata",
];

const ID_PATTERN = /^[a-z][a-z0-9._-]{2,63}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+(?:[-+][a-z0-9.-]+)?$/;
const BINDING_PATTERN = /^(?:Ctrl|Alt|Shift|Meta)\+[A-Za-z0-9]{1,16}$/;
const ROUTE_PATTERN = /^[a-z][a-z0-9/_-]{1,63}$/;
const PANEL_LOCATIONS = ["sidebar", "inspector", "dashboard", "console"];
const WRITE_ACTIONS = [
  "extensions.install",
  "extensions.remove",
  "extensions.reset",
];

function record(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    return null;
  return value as Record<string, unknown>;
}

export function safeParseJson<T = unknown>(text: string): ParsedJson<T> {
  if (!text.trim()) return { value: null, error: "Enter JSON data", ok: false };
  try {
    const value = JSON.parse(text) as T;
    return { value, error: "", ok: true };
  } catch (error) {
    return {
      value: null,
      error: error instanceof Error ? error.message : "Invalid JSON",
      ok: false,
    };
  }
}

function issue(path: string, code: string, message: string): ValidationIssue {
  return { path, code, message, severity: "error" };
}

function cleanText(value: unknown, limit = 240): string {
  if (typeof value !== "string") return "";
  return value
    .trim()
    .replace(/\s+/g, " ")
    .slice(0, limit + 1);
}

export function exampleManifestValue(): ExtensionManifest {
  return {
    schema: MANIFEST_SCHEMA_ID,
    id: "example.panel",
    version: "1.0.0",
    title: "Example Panel",
    summary: "Declares UI contributions only; no code is shipped or run.",
    requires: ["extensions"],
    contributions: [
      {
        kind: "panel",
        id: "example-panel",
        title: "Example",
        location: "sidebar",
        description: "A read-only summary panel.",
      },
      {
        kind: "command",
        id: "example-refresh",
        title: "Refresh example panel",
        group: "Extensions",
      },
    ],
    metadata: { origin: "local" },
  };
}

export function exampleManifestText(): string {
  return JSON.stringify(exampleManifestValue(), null, 2);
}

function walkData(
  value: unknown,
  path: string,
  issues: ValidationIssue[],
  depth = 0,
): void {
  if (depth > 8) {
    issues.push(issue(path, "too_deep", "Manifest nesting is too deep"));
    return;
  }
  const objectValue = record(value);
  if (objectValue) {
    for (const [key, child] of Object.entries(objectValue)) {
      const childPath = path ? `${path}.${key}` : key;
      if (FORBIDDEN_KEYS.includes(key.toLowerCase())) {
        issues.push(
          issue(childPath, "forbidden_key", `Key '${key}' is not data-only`),
        );
      }
      walkData(child, childPath, issues, depth + 1);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) =>
      walkData(child, `${path}[${index}]`, issues, depth + 1),
    );
  }
}

function validateContribution(
  raw: unknown,
  _index: number,
  seen: Set<string>,
): Record<string, unknown> | null {
  const objectValue = record(raw);
  if (!objectValue) {
    return null;
  }
  const kind = objectValue.kind;
  if (
    typeof kind !== "string" ||
    !CONTRIBUTION_KINDS.includes(kind as ContributionKind)
  ) {
    return null;
  }
  const normalized: Record<string, unknown> = { kind };
  for (const key of ["id", "title", "description", "group"]) {
    const text = cleanText(objectValue[key]);
    if (text) normalized[key] = text;
  }
  const identifier = String(normalized.id ?? "");
  if (identifier && seen.has(identifier)) {
    return null;
  }
  if (identifier) seen.add(identifier);
  if (kind === "panel") {
    const location = objectValue.location;
    if (typeof location !== "string" || !PANEL_LOCATIONS.includes(location))
      return null;
    normalized.location = location;
  }
  if (kind === "shortcut") {
    const binding = objectValue.binding;
    if (typeof binding !== "string" || !BINDING_PATTERN.test(binding))
      return null;
    normalized.binding = binding;
  }
  if (kind === "view") {
    const route = objectValue.route;
    if (typeof route !== "string" || !ROUTE_PATTERN.test(route)) return null;
    normalized.route = route;
  }
  if (kind === "theme") {
    const tokens = record(objectValue.tokens);
    if (tokens) normalized.tokens = { ...tokens };
  }
  return normalized;
}

export function validateManifest(value: unknown): ValidationReport {
  const issues: ValidationIssue[] = [];
  const objectValue = record(value);
  if (!objectValue) {
    issues.push(
      issue("manifest", "invalid_type", "Manifest must be an object"),
    );
    return { valid: false, issues, fingerprint: "" };
  }
  walkData(objectValue, "", issues);

  for (const key of Object.keys(objectValue)) {
    if (!TOP_LEVEL_FIELDS.includes(key)) {
      issues.push(
        issue(key, "unknown_field", "Field is not part of the schema"),
      );
    }
  }

  const requireText = (key: string, limit = 240): string => {
    const text = cleanText(objectValue[key], limit);
    if (!text) issues.push(issue(key, "missing_field", "Field is required"));
    return text;
  };
  const schema = requireText("schema");
  if (schema && schema !== MANIFEST_SCHEMA_ID) {
    issues.push(
      issue("schema", "invalid_choice", `Expected ${MANIFEST_SCHEMA_ID}`),
    );
  }
  const id = requireText("id");
  if (id && !ID_PATTERN.test(id)) {
    issues.push(issue("id", "invalid_choice", "Invalid extension id"));
  }
  const version = requireText("version");
  if (version && !VERSION_PATTERN.test(version)) {
    issues.push(issue("version", "invalid_choice", "Version must be semantic"));
  }
  const title = requireText("title");
  const summary =
    typeof objectValue.summary === "string" ? objectValue.summary : "";

  const requires: string[] = [];
  if (!Array.isArray(objectValue.requires)) {
    issues.push(issue("requires", "invalid_type", "Requires must be a list"));
  } else {
    for (const capability of objectValue.requires) {
      if (typeof capability !== "string" || capability.length < 2) {
        issues.push(issue("requires", "invalid_choice", "Invalid capability"));
      } else {
        requires.push(capability);
      }
    }
  }

  const normalizedContributions: Record<string, unknown>[] = [];
  const seen = new Set<string>();
  if (!Array.isArray(objectValue.contributions)) {
    issues.push(
      issue("contributions", "invalid_type", "Contributions must be a list"),
    );
  } else if (objectValue.contributions.length === 0) {
    issues.push(
      issue(
        "contributions",
        "missing_field",
        "At least one contribution is required",
      ),
    );
  } else if (objectValue.contributions.length > MAX_CONTRIBUTIONS) {
    issues.push(
      issue("contributions", "field_too_long", "Too many contributions"),
    );
  } else {
    objectValue.contributions.forEach((raw, index) => {
      const contribution = validateContribution(raw, index, seen);
      if (!contribution) {
        issues.push(
          issue(
            `contributions[${index}]`,
            "invalid_choice",
            "Invalid contribution",
          ),
        );
      } else {
        normalizedContributions.push(contribution);
      }
    });
  }

  const normalized: ExtensionManifest = {
    schema,
    id,
    version,
    title,
    summary,
    requires: [...new Set(requires)].sort(),
    contributions:
      normalizedContributions as unknown as ExtensionManifest["contributions"],
    metadata: (record(objectValue.metadata) ?? {}) as Record<string, unknown>,
  };
  const errors = issues.filter((item) => item.severity === "error");
  return {
    valid: errors.length === 0,
    issues,
    normalized,
    fingerprint: errors.length === 0 ? fingerprintOf(normalized) : "",
  };
}

function canonicalText(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalText).join(",")}]`;
  const objectValue = record(value);
  if (objectValue) {
    const parts = Object.keys(objectValue)
      .sort()
      .map(
        (key) => `${JSON.stringify(key)}:${canonicalText(objectValue[key])}`,
      );
    return `{${parts.join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function fingerprintOf(value: unknown): string {
  let hash = 2166136261;
  const text = canonicalText(value);
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return `"${hash.toString(16)}"`;
}

export function issueSummary(report: ValidationReport): string {
  if (report.valid) return "Manifest is a valid data-only declaration.";
  return report.issues
    .map((item) => `${item.path}: ${item.message}`)
    .join(" · ");
}

export function isWriteRoute(namespace: string, action: string): boolean {
  return WRITE_ACTIONS.includes(`${namespace}.${action}`);
}

export function guardWrite(request: ExplorerRequest): string {
  if (isWriteRoute(request.namespace, request.action) && !request.allowWrite) {
    return "Write route requires the explicit write opt-in checkbox.";
  }
  return "";
}

export function requestBody(
  request: ExplorerRequest,
): ParsedJson<Record<string, unknown>> {
  const parsed = safeParseJson<Record<string, unknown>>(
    request.bodyText || "{}",
  );
  if (!parsed.ok) return parsed;
  const body = record(parsed.value);
  if (!body) {
    return {
      value: null,
      error: "Request body must be a JSON object",
      ok: false,
    };
  }
  return { value: body, error: "", ok: true };
}

export function previewResponse(response: ExplorerResponse | null): string {
  if (!response) return "";
  const text = JSON.stringify(
    response.data ?? { error: response.errorMessage },
    null,
    2,
  );
  return text.length > 600 ? `${text.slice(0, 600)}…` : text;
}

export function pushEntry(
  entries: ConsoleEntry[],
  entry: ConsoleEntry,
  limit = MAX_HISTORY,
): ConsoleEntry[] {
  const next = [...entries, entry];
  return next.length > limit ? next.slice(next.length - limit) : next;
}

export function filterEntries(
  entries: ConsoleEntry[],
  query = "",
  errorsOnly = false,
): ConsoleEntry[] {
  const needle = query.trim().toLowerCase();
  return entries.filter((entry) => {
    if (errorsOnly && !entry.errorCode) return false;
    if (!needle) return true;
    return (
      entry.route.toLowerCase().includes(needle) ||
      entry.errorCode.toLowerCase().includes(needle) ||
      entry.requestId.toLowerCase().includes(needle)
    );
  });
}

export function formatDuration(durationMs: number): string {
  return `${Math.max(0, Math.round(durationMs))} ms`;
}

export function deniedCapabilities(map: Record<string, boolean>): string[] {
  return Object.keys(map)
    .filter((name) => map[name] === false)
    .sort();
}

export function capabilitySummary(decisions: CapabilityDecision[]): string {
  const granted = decisions.filter((item) => item.granted).length;
  return `${granted}/${decisions.length} capabilities available`;
}

export function responseTone(response: ExplorerResponse | null): string {
  if (!response) return "idle";
  if (!response.ok) return "error";
  if (response.status === 304) return "cached";
  return "success";
}
