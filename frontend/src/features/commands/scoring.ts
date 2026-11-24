/** Deterministic scoring and grouping of command results. */

import type {
  CommandContext,
  CommandGroup,
  CommandGroupResult,
  CommandHit,
  CommandSpec,
} from "./types";

const WEIGHTS = {
  exact: 6,
  prefix: 3,
  word: 2,
  contains: 1.2,
  subsequence: 0.8,
  keyword: 1.6,
  alias: 2.4,
  group: 0.5,
  context: 2,
  usage: 2.2,
} as const;

const THRESHOLD = 0.7;

export interface CommandScore {
  command_id: string;
  score: number;
  signals: string[];
  matched_text: string;
}

export function normalize(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

export function tokenizeQuery(query: string): string[] {
  return normalize(query).match(/[a-z0-9]+/g) ?? [];
}

export function subsequenceRatio(query: string, text: string): number {
  const needle = normalize(query).replace(/\s/g, "");
  const haystack = normalize(text).replace(/\s/g, "");
  if (!needle || !haystack) return 0;
  let cursor = 0;
  let matched = 0;
  for (const char of haystack) {
    if (cursor < needle.length && char === needle[cursor]) {
      matched += 1;
      cursor += 1;
    }
  }
  return matched / needle.length;
}

export function contextWeight(
  spec: CommandSpec,
  context: CommandContext,
): number {
  let boost = 0;
  const entityKinds = [
    context.entity?.kind,
    ...context.selection.map((item) => item.kind),
  ];
  if (spec.target_kind && entityKinds.includes(spec.target_kind)) boost += 0.45;
  if (context.focus_active && spec.group === "session") boost += 0.3;
  if (!context.focus_active && spec.group === "session") boost -= 0.1;
  if (context.selection.length && spec.group === "inspect") boost += 0.15;
  if (spec.requires_selection && context.selection.length) boost += 0.1;
  return boost;
}

export function scoreCommand(
  query: string,
  spec: CommandSpec,
  context: CommandContext,
  usageScore = 0,
): CommandScore {
  const needle = normalize(query);
  const title = normalize(spec.title);
  const commandId = normalize(spec.id);
  const group = normalize(spec.group);
  const signals: string[] = [];
  let exact = 0;
  let prefix = 0;
  let word = 0;
  let contains = 0;
  let subsequence = 0;
  let keyword = 0;
  let alias = 0;
  let groupScore = 0;
  let matched = "";
  if (needle) {
    for (const [candidate, label] of [
      [title, "title"],
      [commandId, "id"],
      [spec.id.split(".").slice(-1)[0], "action"],
    ]) {
      if (candidate === needle) {
        exact = 1;
        matched = candidate;
        signals.push(`exact:${label}`);
        break;
      }
      if (candidate.startsWith(needle)) {
        prefix = 1;
        matched = matched || candidate;
        signals.push(`prefix:${label}`);
      } else if (candidate.includes(needle)) {
        contains = 1;
        matched = matched || candidate;
        signals.push(`contains:${label}`);
      }
      if (label === "title" || label === "action") {
        subsequence = Math.max(
          subsequence,
          subsequenceRatio(needle, candidate),
        );
      }
    }
    for (const token of tokenizeQuery(query)) {
      if (
        title.split(" ").includes(token) ||
        commandId.replace(/\./g, " ").split(" ").includes(token)
      ) {
        word += 1;
        signals.push(`word:${token}`);
      }
    }
    for (const term of spec.keywords) {
      if (term.startsWith(needle) || term.includes(needle)) {
        keyword = 1;
        signals.push(`keyword:${term}`);
      }
    }
    for (const candidate of spec.aliases) {
      const value = normalize(candidate);
      if (value === needle || value.startsWith(needle)) {
        alias = 1;
        matched = matched || value;
        signals.push(`alias:${candidate}`);
      }
    }
    if (group.includes(needle)) {
      groupScore = 1;
      signals.push("group");
    }
  }
  if (!signals.length && needle && subsequence < THRESHOLD) {
    return {
      command_id: spec.id,
      score: 0,
      signals: [],
      matched_text: matched,
    };
  }
  if (subsequence >= THRESHOLD) signals.push("subsequence");
  const contextBoost = contextWeight(spec, context);
  if (contextBoost) signals.push("context");
  if (usageScore > 0.15) signals.push("frequent");
  const score =
    exact * WEIGHTS.exact +
    prefix * WEIGHTS.prefix +
    Math.min(word, 2) * WEIGHTS.word +
    contains * WEIGHTS.contains +
    (subsequence >= THRESHOLD ? subsequence : 0) * WEIGHTS.subsequence +
    keyword * WEIGHTS.keyword +
    alias * WEIGHTS.alias +
    groupScore * WEIGHTS.group +
    contextBoost * WEIGHTS.context +
    usageScore * WEIGHTS.usage;
  return {
    command_id: spec.id,
    score: Math.round(score * 10000) / 10000,
    signals: Array.from(new Set(signals)),
    matched_text: matched,
  };
}

export function isCommandAvailable(
  spec: CommandSpec,
  context: CommandContext,
): boolean {
  if (spec.status !== "enabled") return false;
  if (
    !context.capabilities.includes("commands") ||
    !context.capabilities.includes(spec.capability)
  ) {
    return false;
  }
  if (spec.requires_selection && !context.selection.length) return false;
  if (spec.target_kind) {
    const kinds = [
      context.entity?.kind,
      ...context.selection.map((item) => item.kind),
    ];
    if (!kinds.includes(spec.target_kind)) return false;
  }
  return true;
}

const GROUP_ORDER: CommandGroup[] = [
  "navigation",
  "create",
  "inspect",
  "edit",
  "view",
  "session",
  "automation",
  "system",
];

export function rankCommands(
  query: string,
  specs: CommandSpec[],
  context: CommandContext,
  options: { usage?: (id: string) => number; limit?: number } = {},
): CommandHit[] {
  const limit = options.limit ?? 12;
  if (limit < 1) throw new Error("limit must be positive");
  const hits: CommandHit[] = [];
  for (const spec of specs) {
    if (!isCommandAvailable(spec, context)) continue;
    const result = scoreCommand(
      query,
      spec,
      context,
      options.usage?.(spec.id) ?? 0,
    );
    if (result.score > 0 || !query.trim()) {
      hits.push({
        command: spec,
        score: result.score,
        signals: result.signals,
        matched_text: result.matched_text,
      });
    }
  }
  hits.sort(
    (a, b) =>
      b.score - a.score ||
      GROUP_ORDER.indexOf(a.command.group) -
        GROUP_ORDER.indexOf(b.command.group) ||
      a.command.order - b.command.order ||
      a.command.id.localeCompare(b.command.id),
  );
  return hits.slice(0, limit);
}

export function groupHits(
  hits: CommandHit[],
  limitPerGroup = 6,
): CommandGroupResult[] {
  if (limitPerGroup < 1) throw new Error("limit_per_group must be positive");
  const buckets = new Map<CommandGroup, CommandHit[]>();
  for (const hit of hits) {
    const bucket = buckets.get(hit.command.group) ?? [];
    bucket.push(hit);
    buckets.set(hit.command.group, bucket);
  }
  return Array.from(buckets.entries())
    .sort((a, b) => GROUP_ORDER.indexOf(a[0]) - GROUP_ORDER.indexOf(b[0]))
    .map(([group, values]) => ({
      group,
      label: group
        .replace(/_/g, " ")
        .replace(/^./, (char) => char.toUpperCase()),
      hits: values.slice(0, limitPerGroup),
    }));
}
