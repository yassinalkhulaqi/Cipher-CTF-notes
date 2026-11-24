/** Typed variable validation and template interpolation for the variable form. */

import type { ValidationIssue, VariableDef } from "./types";
import { issue } from "./types";

export type VarValue = unknown;

export interface VariableResolution {
  values: Record<string, VarValue>;
  issues: ValidationIssue[];
  ok: boolean;
  secrets: string[];
}

const PLACEHOLDER = /\{\{\s*([^{}]+?)\s*\}\}/g;

export function collectPlaceholders(template: string): string[] {
  const found = new Set<string>();
  for (const match of template.matchAll(PLACEHOLDER)) found.add((match[1] ?? "").trim());
  return Array.from(found);
}

function lookup(context: Record<string, unknown>, path: string): { found: boolean; value: unknown } {
  const parts = path.split(".");
  const root = parts[0] ?? "";
  let current: unknown;
  let remainder: string[];
  if (root === "vars" || root === "steps") {
    current = context[root];
    remainder = parts.slice(1);
  } else {
    current = context["vars"];
    remainder = parts;
    if (current && typeof current === "object" && !(root in (current as Record<string, unknown>)) && root in context) {
      current = context;
    }
  }
  for (const part of remainder) {
    if (current && typeof current === "object" && part in (current as Record<string, object>)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return { found: false, value: undefined };
    }
  }
  return { found: true, value: current };
}

export function asText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function interpolate(template: string, context: Record<string, unknown>, strict = true): unknown {
  const matches = Array.from(template.matchAll(PLACEHOLDER));
  if (!matches.length) return template;
  const first = matches[0];
  if (matches.length === 1 && first && first.index === 0 && (first.index + first[0].length) === template.length) {
    const resolved = lookup(context, (first[1] ?? "").trim());
    if (!resolved.found) {
      if (strict) throw new Error(`Unresolved variable: ${(first[1] ?? "").trim()}`);
      return "";
    }
    return structuredClone(resolved.value);
  }
  return template.replace(PLACEHOLDER, (_whole, key: string) => {
    const resolved = lookup(context, key.trim());
    if (!resolved.found) {
      if (strict) throw new Error(`Unresolved variable: ${key.trim()}`);
      return "";
    }
    return asText(resolved.value);
  });
}

function coerce(value: unknown, definition: VariableDef, path: string): { value: unknown; issue: ValidationIssue | null } {
  const kind = definition.kind ?? "text";
  if (kind === "number") {
    const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : Number.NaN;
    if (!Number.isFinite(numeric)) {
      return { value, issue: issue("invalid_type", `Expected a number for ${definition.key}`, path) };
    }
    if (definition.minimum !== undefined && numeric < definition.minimum) {
      return { value, issue: issue("out_of_range", `${definition.key} is below its minimum`, path) };
    }
    if (definition.maximum !== undefined && numeric > definition.maximum) {
      return { value, issue: issue("out_of_range", `${definition.key} is above its maximum`, path) };
    }
    return { value: numeric, issue: null };
  }
  if (kind === "boolean") {
    if (typeof value === "boolean") return { value, issue: null };
    if (typeof value === "number" && (value === 0 || value === 1)) return { value: Boolean(value), issue: null };
    if (typeof value === "string" && ["true", "false", "yes", "no", "on", "off", "1", "0"].includes(value.toLowerCase())) {
      return { value: ["true", "yes", "on", "1"].includes(value.toLowerCase()), issue: null };
    }
    return { value, issue: issue("invalid_type", `Expected a boolean for ${definition.key}`, path) };
  }
  if (kind === "choice") {
    const text = asText(value);
    if (!(definition.choices ?? []).includes(text)) {
      return { value, issue: issue("invalid_choice", `${definition.key} must be one of: ${(definition.choices ?? []).join(", ")}`, path) };
    }
    return { value: text, issue: null };
  }
  if (kind === "list") {
    if (Array.isArray(value)) return { value: structuredClone(value), issue: null };
    if (typeof value === "string") {
      return { value: value.split(",").map((item) => item.trim()).filter(Boolean), issue: null };
    }
    return { value, issue: issue("invalid_type", `Expected a list for ${definition.key}`, path) };
  }
  if (kind === "entity_ref") {
    const text = asText(value);
    if (!/^[A-Za-z]+:[^\s]+$/.test(text)) {
      return { value, issue: issue("invalid_ref", `${definition.key} must be a kind:value reference`, path) };
    }
    return { value: text, issue: null };
  }
  const text = asText(value);
  if (definition.pattern && !new RegExp(`^(?:${definition.pattern})$`).test(text)) {
    return { value, issue: issue("invalid_pattern", `${definition.key} does not match its pattern`, path) };
  }
  return { value: text, issue: null };
}

export function validateVariableValues(
  definitions: VariableDef[],
  supplied: Record<string, VarValue>,
): VariableResolution {
  const values: Record<string, VarValue> = {};
  const issues: ValidationIssue[] = [];
  const known = new Set(definitions.map((definition) => definition.key));
  for (const key of Object.keys(supplied).sort()) {
    if (!known.has(key)) issues.push(issue("unknown_variable", `Unknown variable: ${key}`, `variables.${key}`));
  }
  for (const definition of definitions) {
    const path = `variables.${definition.key}`;
    if (definition.required && !(definition.key in supplied)) {
      issues.push(issue("missing_variable", `Missing required variable: ${definition.key}`, path));
      continue;
    }
    const raw = definition.key in supplied ? supplied[definition.key] : (definition.default ?? "");
    const result = coerce(raw, definition, path);
    if (result.issue) issues.push(result.issue);
    values[definition.key] = result.value;
  }
  return {
    values,
    issues,
    ok: !issues.some((item) => item.severity === "error"),
    secrets: definitions.filter((definition) => definition.secret).map((definition) => definition.key),
  };
}

export function resolveInputs(
  inputs: Record<string, unknown>,
  context: Record<string, unknown>,
  strict = true,
): Record<string, unknown> {
  const resolve = (value: unknown): unknown => {
    if (typeof value === "string") return interpolate(value, context, strict);
    if (Array.isArray(value)) return value.map(resolve);
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, resolve(item)]),
      );
    }
    return structuredClone(value);
  };
  return Object.fromEntries(Object.entries(inputs).map(([key, value]) => [key, resolve(value)]));
}

export function safeValues(resolution: VariableResolution): Record<string, VarValue> {
  return Object.fromEntries(
    Object.entries(resolution.values).map(([key, value]) => [
      key,
      resolution.secrets.includes(key) ? "***" : value,
    ]),
  );
}

export function variableIssuesByKey(issues: ValidationIssue[]): Record<string, ValidationIssue> {
  const result: Record<string, ValidationIssue> = {};
  for (const item of issues) {
    const key = item.path.split(".")[1] ?? "";
    if (key && !(key in result)) result[key] = item;
  }
  return result;
}
