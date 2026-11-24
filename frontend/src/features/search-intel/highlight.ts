/** Pure fragment chunking shared by the highlight renderer and tests. */

import type { FragmentV2, HighlightV2 } from "./types";

export interface FragmentChunk {
  text: string;
  match: boolean;
}

export function splitFragment(fragment: FragmentV2): FragmentChunk[] {
  const text = fragment.text;
  if (!fragment.highlights.length) return text ? [{ text, match: false }] : [];
  const spans = fragment.highlights
    .map((highlight: HighlightV2) => ({
      start: Math.max(0, Math.min(text.length, highlight.start)),
      end: Math.max(0, Math.min(text.length, highlight.end)),
    }))
    .filter((span) => span.end > span.start)
    .sort((a, b) => a.start - b.start);
  const chunks: FragmentChunk[] = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start < cursor) continue;
    if (span.start > cursor) {
      chunks.push({ text: text.slice(cursor, span.start), match: false });
    }
    chunks.push({ text: text.slice(span.start, span.end), match: true });
    cursor = span.end;
  }
  if (cursor < text.length)
    chunks.push({ text: text.slice(cursor), match: false });
  return chunks;
}

export function fragmentPreview(fragment: FragmentV2): string {
  const prefix = fragment.prefix ? "…" : "";
  const suffix = fragment.suffix ? "…" : "";
  return `${prefix}${fragment.text}${suffix}`;
}
