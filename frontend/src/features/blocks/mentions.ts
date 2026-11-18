import { normalizeMentionTarget, normalizeWhitespace } from "./normalize";
import {
  type Block,
  type Mention,
  type MentionKind,
  type MentionSuggestion,
} from "./types";

const MENTION_RE =
  /@\[([^\]\n]{1,80})\]\(([a-z][a-z0-9_-]{0,31}):([^\s)]{1,128})\)/gi;

function asMentionKind(value: string): MentionKind | null {
  const allowed: MentionKind[] = [
    "note",
    "user",
    "target",
    "finding",
    "evidence",
    "tag",
  ];
  return allowed.includes(value as MentionKind) ? (value as MentionKind) : null;
}

export function extractMentions(text: string, blockId = ""): Mention[] {
  const mentions: Mention[] = [];
  for (const match of text.matchAll(MENTION_RE)) {
    const kind = asMentionKind(match[2].toLowerCase());
    const label = match[1].trim();
    const target = match[3].trim();
    if (!kind || !label || !target) continue;
    const start = match.index ?? 0;
    mentions.push({
      kind,
      target,
      label,
      start,
      end: start + match[0].length,
      blockId,
    });
  }
  return mentions;
}

export function refreshMentions(block: Block): Block {
  return { ...block, mentions: extractMentions(block.text, block.id) };
}

export function renderMention(
  kind: MentionKind,
  target: string,
  label: string,
): string {
  return `@[${label}](${kind}:${target})`;
}

export function replaceMentionTargets(
  text: string,
  replacements: Record<string, string>,
): string {
  return text.replace(
    MENTION_RE,
    (token, label: string, kind: string, target: string) => {
      const replacement = replacements[`${kind}:${target}`];
      if (!replacement) return token;
      const validKind = asMentionKind(kind);
      return validKind ? renderMention(validKind, replacement, label) : token;
    },
  );
}

export function mentionTargets(
  mentions: Mention[],
  kind?: MentionKind,
): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const mention of mentions) {
    if (kind && mention.kind !== kind) continue;
    const key = `${mention.kind}:${mention.target}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(mention.target);
  }
  return result;
}

function rank(candidate: string, query: string): number {
  const haystack = candidate.toLowerCase();
  const needle = normalizeWhitespace(query).toLowerCase();
  if (!needle) return 1;
  if (haystack === needle) return 100;
  if (haystack.startsWith(needle))
    return 80 - Math.min(20, haystack.length - needle.length);
  const index = haystack.indexOf(needle);
  if (index >= 0) return 50 - Math.min(20, index);
  return 0;
}

interface IndexedMention {
  kind: MentionKind;
  target: string;
  label: string;
  owners: Set<string>;
}

export class MentionIndex {
  private readonly entries = new Map<string, IndexedMention>();

  add(blockId: string, mentions: Mention[]): number {
    let added = 0;
    for (const mention of mentions) {
      const key = `${mention.kind}:${mention.target}`;
      const existing = this.entries.get(key);
      if (existing) {
        existing.owners.add(blockId);
        continue;
      }
      this.entries.set(key, {
        kind: mention.kind,
        target: mention.target,
        label: mention.label,
        owners: new Set([blockId]),
      });
      added += 1;
    }
    return added;
  }

  remove(blockId: string): number {
    let removed = 0;
    for (const [key, entry] of Array.from(this.entries.entries())) {
      if (!entry.owners.delete(blockId)) continue;
      if (entry.owners.size === 0) {
        this.entries.delete(key);
        removed += 1;
      }
    }
    return removed;
  }

  forTarget(target: string, kind?: MentionKind): Mention[] {
    const result: Mention[] = [];
    for (const entry of this.entries.values()) {
      if (entry.target.toLowerCase() !== target.toLowerCase()) continue;
      if (kind && entry.kind !== kind) continue;
      for (const blockId of Array.from(entry.owners).sort()) {
        result.push({
          kind: entry.kind,
          target: entry.target,
          label: entry.label,
          start: 0,
          end: 0,
          blockId,
        });
      }
    }
    return result;
  }

  suggestions(
    query: string,
    kind?: MentionKind,
    limit = 12,
  ): MentionSuggestion[] {
    const result: MentionSuggestion[] = [];
    for (const entry of this.entries.values()) {
      if (kind && entry.kind !== kind) continue;
      const score = Math.max(
        rank(entry.target, query),
        rank(entry.label, query),
      );
      if (score > 0) {
        result.push({
          kind: entry.kind,
          target: entry.target,
          label: entry.label,
          score,
        });
      }
    }
    result.sort(
      (left, right) =>
        right.score - left.score ||
        left.kind.localeCompare(right.kind) ||
        left.target.localeCompare(right.target),
    );
    return result.slice(0, Math.max(0, limit));
  }

  clear(): void {
    this.entries.clear();
  }

  get size(): number {
    return this.entries.size;
  }

  targets(): string[] {
    return Array.from(this.entries.values(), (entry) => entry.target).sort();
  }
}

export function buildMentionIndex(blocks: Block[]): MentionIndex {
  const index = new MentionIndex();
  for (const block of blocks) index.add(block.id, block.mentions);
  return index;
}

export function mentionAutocomplete(
  query: string,
  blocks: Block[],
  limit = 12,
): MentionSuggestion[] {
  return buildMentionIndex(blocks).suggestions(query, undefined, limit);
}

export function normalizeMention(
  kind: string,
  target: string,
  label: string,
): Mention {
  const validKind = asMentionKind(kind.toLowerCase()) ?? "note";
  const cleanedTarget = normalizeMentionTarget(target);
  return {
    kind: validKind,
    target: cleanedTarget,
    label: normalizeWhitespace(label) || cleanedTarget,
    start: 0,
    end: 0,
    blockId: "",
  };
}

export function mentionKey(mention: Mention): string {
  return `${mention.kind}:${mention.target.toLowerCase()}`;
}
