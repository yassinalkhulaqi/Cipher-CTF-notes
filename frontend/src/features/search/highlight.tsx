import { Fragment, type ReactNode } from "react";
import { foldText, normalizeToken, stemToken } from "./query";
import type { SearchHighlight, SearchSnippet, SearchTextChunk } from "./types";

export interface TextSegment {
  text: string;
  match: boolean;
  kind: string;
}

export function mergeHighlights(
  highlights: SearchHighlight[],
): SearchHighlight[] {
  const ordered = [...highlights].sort(
    (a, b) => a.start - b.start || a.end - b.end,
  );
  const merged: SearchHighlight[] = [];
  for (const highlight of ordered) {
    if (highlight.end <= highlight.start) continue;
    const previous = merged[merged.length - 1];
    if (previous && highlight.start <= previous.end) {
      previous.end = Math.max(previous.end, highlight.end);
      previous.kind =
        previous.kind === highlight.kind ? previous.kind : "mixed";
      continue;
    }
    merged.push({ ...highlight });
  }
  return merged;
}

export function findTermMatches(text: string, term: string): SearchHighlight[] {
  const needle = stemToken(term);
  if (!needle) return [];
  const folded = foldText(text);
  const results: SearchHighlight[] = [];
  const wordPattern = /[\p{L}\p{N}]+/gu;
  for (const match of text.matchAll(wordPattern)) {
    const start = match.index ?? 0;
    const candidate = stemToken(match[0]);
    if (
      candidate === needle ||
      (needle.length >= 3 && candidate.startsWith(needle))
    ) {
      results.push({
        start,
        end: start + match[0].length,
        term,
        kind: candidate === needle ? "exact" : "prefix",
      });
    }
  }
  if (!results.length && needle.includes(" ")) {
    const position = folded.indexOf(needle);
    if (position >= 0) {
      results.push({
        start: position,
        end: Math.min(text.length, position + needle.length),
        term,
        kind: "phrase",
      });
    }
  }
  return results;
}

export function buildHighlightSegments(
  text: string,
  terms: string[],
): TextSegment[] {
  const highlights = mergeHighlights(
    terms.flatMap((term) => findTermMatches(text, term)),
  );
  return segmentsFromHighlights(text, highlights);
}

export function segmentsFromHighlights(
  text: string,
  highlights: SearchHighlight[],
): TextSegment[] {
  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const highlight of mergeHighlights(highlights)) {
    const start = Math.max(0, Math.min(text.length, highlight.start));
    const end = Math.max(start, Math.min(text.length, highlight.end));
    if (start > cursor) {
      segments.push({
        text: text.slice(cursor, start),
        match: false,
        kind: "text",
      });
    }
    if (end > start) {
      segments.push({
        text: text.slice(start, end),
        match: true,
        kind: highlight.kind,
      });
    }
    cursor = end;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), match: false, kind: "text" });
  }
  return segments;
}

export function chunkToSegments(chunks: SearchTextChunk[]): TextSegment[] {
  return chunks.map((chunk) => ({
    text: chunk.text,
    match: chunk.match,
    kind: chunk.match ? "term" : "text",
  }));
}

export function snippetSegments(snippet: SearchSnippet): TextSegment[] {
  return snippet.chunks?.length
    ? chunkToSegments(snippet.chunks)
    : segmentsFromHighlights(snippet.text, snippet.highlights);
}

export function plainText(segments: TextSegment[]): string {
  return segments.map((segment) => segment.text).join("");
}

export function matchedText(segments: TextSegment[]): string[] {
  return segments
    .filter((segment) => segment.match)
    .map((segment) => segment.text);
}

export function escapeHighlight(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character] ?? character;
  });
}

export function renderHighlightedHtml(text: string, terms: string[]): string {
  return buildHighlightSegments(text, terms)
    .map((segment) =>
      segment.match
        ? `<mark>${escapeHighlight(segment.text)}</mark>`
        : escapeHighlight(segment.text),
    )
    .join("");
}

export interface HighlightedTextProps {
  text: string;
  terms?: string[];
  segments?: TextSegment[];
  className?: string;
  markClassName?: string;
}

export function HighlightedText({
  text,
  terms = [],
  segments,
  className,
  markClassName,
}: HighlightedTextProps): ReactNode {
  const values = segments ?? buildHighlightSegments(text, terms);
  return (
    <span className={className}>
      {values.map((segment, index) =>
        segment.match ? (
          <mark className={markClassName} key={`${index}-${segment.text}`}>
            {segment.text}
          </mark>
        ) : (
          <Fragment key={`${index}-${segment.text}`}>{segment.text}</Fragment>
        ),
      )}
    </span>
  );
}

export function fuzzyTermMatch(term: string, candidate: string): boolean {
  const left = normalizeToken(term);
  const right = normalizeToken(candidate);
  if (!left || !right || Math.abs(left.length - right.length) > 1) return false;
  if (left === right) return true;
  if (left.length < 4) return false;
  let leftIndex = 0;
  let rightIndex = 0;
  let edits = 0;
  while (leftIndex < left.length && rightIndex < right.length) {
    if (left[leftIndex] === right[rightIndex]) {
      leftIndex += 1;
      rightIndex += 1;
      continue;
    }
    edits += 1;
    if (edits > 1) return false;
    if (left.length > right.length) leftIndex += 1;
    else if (right.length > left.length) rightIndex += 1;
    else {
      leftIndex += 1;
      rightIndex += 1;
    }
  }
  return true;
}
