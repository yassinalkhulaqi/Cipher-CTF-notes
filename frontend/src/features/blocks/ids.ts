import { BLOCK_LIMITS } from "./types";

let sequence = 0;

function randomPart(): string {
  const globalCrypto = typeof crypto === "undefined" ? undefined : crypto;
  if (globalCrypto && typeof globalCrypto.getRandomValues === "function") {
    const values = new Uint32Array(2);
    globalCrypto.getRandomValues(values);
    return Array.from(values, (value) =>
      value.toString(16).padStart(8, "0"),
    ).join("");
  }
  const first = Math.floor(Math.random() * 0xffffffff)
    .toString(16)
    .padStart(8, "0");
  const second = Math.floor(Math.random() * 0xffffffff)
    .toString(16)
    .padStart(8, "0");
  return `${first}${second}`;
}

export function blockId(prefix = "blk"): string {
  sequence += 1;
  const clean = prefix.replace(/[^a-zA-Z0-9]+/g, "").toLowerCase() || "blk";
  return `${clean}-${randomPart()}${sequence.toString(36)}`;
}

export function documentId(prefix = "doc"): string {
  sequence += 1;
  const clean = prefix.replace(/[^a-zA-Z0-9]+/g, "").toLowerCase() || "doc";
  return `${clean}-${randomPart()}${sequence.toString(36)}`;
}

export function noteDocumentId(noteId: number): string {
  return `note-${noteId}`;
}

export function noteIdFromDocument(id: string): number | null {
  if (!id.startsWith("note-")) return null;
  const suffix = id.slice(5);
  return /^\d+$/.test(suffix) ? Number(suffix) : null;
}

export function isSafeId(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value);
}

export function normalizeId(value: string, prefix = "blk"): string {
  const trimmed = value.trim();
  if (isSafeId(trimmed)) return trimmed.slice(0, 128);
  const cleaned = trimmed
    .replace(/[^A-Za-z0-9_.:-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (isSafeId(cleaned)) return cleaned.slice(0, 128);
  return blockId(prefix);
}

export function uniqueIds(ids: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const id of ids) {
    const candidate = normalizeId(id);
    if (seen.has(candidate)) continue;
    seen.add(candidate);
    result.push(candidate);
  }
  return result;
}

export function nextBlockId(ids: string[]): string {
  const taken = new Set(ids);
  let candidate = blockId();
  while (taken.has(candidate)) candidate = blockId();
  return candidate;
}

export function resetIdSequence(value = 0): void {
  sequence = Math.max(0, Math.floor(value));
}

export function idSequence(): number {
  return sequence;
}

export function capIds(ids: string[]): string[] {
  return ids.slice(0, BLOCK_LIMITS.maxBlocks);
}
