/** Timeline rendering and field-level diffs for traces and run history. */

import type {
  DiffEntry,
  DryRunTrace,
  RunRecord,
  TimelineItem,
  TraceEntry,
} from "./types";

export function toneFor(status: string): TimelineItem["tone"] {
  if (status === "executed") return "good";
  if (status === "planned") return "info";
  if (status === "skipped") return "warn";
  if (status === "failed") return "bad";
  return "neutral";
}

export function timeline(trace: DryRunTrace): TimelineItem[] {
  return trace.entries.map((entry) => ({
    index: entry.index,
    step_id: entry.step_id,
    title: entry.step_id,
    status: entry.status,
    kind: entry.kind,
    message: entry.message,
    target: entry.result?.ref ?? "",
    mutation: entry.result?.intent ?? null,
    tone: toneFor(entry.status),
    chain: entry.chain ?? "",
  }));
}

function rowKey(entry: TraceEntry, counts: Record<string, number>): string {
  const occurrence = counts[entry.step_id] ?? 0;
  counts[entry.step_id] = occurrence + 1;
  return `${entry.step_id}[${occurrence}]`;
}

function normalize(
  trace: DryRunTrace,
): Record<string, Record<string, unknown>> {
  const counts: Record<string, number> = {};
  const rows: Record<string, Record<string, unknown>> = {};
  for (const entry of trace.entries) {
    rows[rowKey(entry, counts)] = {
      status: entry.status,
      kind: entry.kind,
      message: entry.message,
      target: entry.result?.ref ?? "",
      intent: entry.result?.intent ?? null,
    };
  }
  return rows;
}

function flatten(value: unknown, prefix = ""): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      const path = `${prefix}[${index}]`;
      if (item && typeof item === "object")
        Object.assign(result, flatten(item, path));
      else result[path] = item;
    });
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(
      value as Record<string, unknown>,
    )) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (item && typeof item === "object")
        Object.assign(result, flatten(item, path));
      else result[path] = item;
    }
  } else if (prefix) {
    result[prefix] = value;
  }
  return result;
}

export function diffTraces(
  first: DryRunTrace,
  second: DryRunTrace,
): DiffEntry[] {
  const left = normalize(first);
  const right = normalize(second);
  const differences: DiffEntry[] = [];
  for (const key of Array.from(
    new Set([...Object.keys(left), ...Object.keys(right)]),
  ).sort()) {
    const before = left[key];
    const after = right[key];
    if (!before || !after) {
      differences.push({
        path: `steps.${key}`,
        before: before ?? null,
        after: after ?? null,
      });
      continue;
    }
    const beforeFields = flatten(before);
    const afterFields = flatten(after);
    for (const path of Array.from(
      new Set([...Object.keys(beforeFields), ...Object.keys(afterFields)]),
    ).sort()) {
      if (
        JSON.stringify(beforeFields[path]) !== JSON.stringify(afterFields[path])
      ) {
        differences.push({
          path: `steps.${key}.${path}`,
          before: beforeFields[path] ?? null,
          after: afterFields[path] ?? null,
        });
      }
    }
  }
  if (first.input_fingerprint !== second.input_fingerprint) {
    differences.push({
      path: "input_fingerprint",
      before: first.input_fingerprint,
      after: second.input_fingerprint,
    });
  }
  return differences;
}

export function asTrace(record: RunRecord): DryRunTrace {
  return {
    playbook_ref: record.playbook_ref,
    mode: record.mode,
    entries: record.trace,
    variables: record.variables,
    digest: record.trace_digest,
    writes: record.trace.filter((entry) => entry.result?.applied).length,
    input_fingerprint: record.input_fingerprint,
    state_digest: record.state_digest,
  };
}

export function diffRuns(first: RunRecord, second: RunRecord): DiffEntry[] {
  const differences: DiffEntry[] = [];
  for (const field of [
    "status",
    "mode",
    "trace_digest",
    "state_digest",
    "rollback_of",
  ] as const) {
    if (first[field] !== second[field]) {
      differences.push({
        path: field,
        before: first[field],
        after: second[field],
      });
    }
  }
  return [...differences, ...diffTraces(asTrace(first), asTrace(second))];
}

export function traceSummary(trace: DryRunTrace): Record<string, number> {
  const summary: Record<string, number> = {
    steps: trace.entries.length,
    mutations: trace.entries.filter((entry) => entry.result).length,
    planned: 0,
    executed: 0,
    skipped: 0,
    failed: 0,
    writes: trace.writes,
  };
  for (const entry of trace.entries)
    summary[entry.status] = (summary[entry.status] ?? 0) + 1;
  return summary;
}

export function traceVerdict(trace: DryRunTrace): "clean" | "attention" {
  if (
    trace.mode === "dry_run" &&
    (trace.writes > 0 ||
      trace.entries.some((entry) => entry.status === "executed"))
  )
    return "attention";
  return trace.entries.some((entry) => entry.status === "failed")
    ? "attention"
    : "clean";
}
