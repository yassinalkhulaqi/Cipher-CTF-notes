/**
 * Tag helpers for the note editor.
 *
 * Tags are stored in notes as a comma-separated string (the backend splits
 * on commas as well). These helpers are the single place that knows how to
 * parse, normalize, add, and remove tags — the properties modal and the tag
 * input both use them.
 */

export const TAG_MAX_COUNT = 24;
export const TAG_MAX_LENGTH = 48;

/** Parse a raw comma-separated string into a normalized, de-duplicated list. */
export function parseTags(raw: string): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const piece of raw.split(",")) {
    const normalized = normalizeTag(piece);
    if (!normalized) continue;
    const key = normalized.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    tags.push(normalized);
  }
  return tags;
}

/** Normalize a single tag: trim, collapse internal whitespace. */
export function normalizeTag(tag: string): string {
  return tag.replace(/\s+/g, " ").trim();
}

/** Serialize a list of tags back to the comma-separated storage format. */
export function serializeTags(tags: string[]): string {
  return parseTags(tags.join(",")).join(", ");
}

/** Whether a tag can be added to the raw list (limits + duplicates). */
export function canAddTag(raw: string, tag: string): boolean {
  const normalized = normalizeTag(tag);
  if (!normalized) return false;
  if (normalized.length > TAG_MAX_LENGTH) return false;
  const existing = parseTags(raw);
  if (existing.length >= TAG_MAX_COUNT) return false;
  return !existing.some((item) => item.toLowerCase() === normalized.toLowerCase());
}

/** Add a tag to a raw list; returns the serialized result (unchanged on refusal). */
export function addTag(raw: string, tag: string): string {
  if (!canAddTag(raw, tag)) return serializeTags(parseTags(raw));
  return serializeTags([...parseTags(raw), normalizeTag(tag)]);
}

/** Remove a tag (case-insensitive) from a raw list. */
export function removeTag(raw: string, tag: string): string {
  const needle = normalizeTag(tag).toLowerCase();
  return serializeTags(parseTags(raw).filter((item) => item.toLowerCase() !== needle));
}

/** Toggle a tag; convenience for chip-style UIs. */
export function toggleTag(raw: string, tag: string): string {
  const needle = normalizeTag(tag).toLowerCase();
  const existing = parseTags(raw);
  return existing.some((item) => item.toLowerCase() === needle)
    ? serializeTags(existing.filter((item) => item.toLowerCase() !== needle))
    : addTag(raw, tag);
}
