import { blockPlainText } from "./blocks";
import { type Block, type BlockDocument, type SearchHit } from "./types";

const TOKEN_RE = /[\p{L}\p{N}_]+/gu;

export function tokenize(text: string): string[] {
  return (text.toLowerCase().match(TOKEN_RE) ?? []).filter(Boolean);
}

export function queryTerms(query: string): string[] {
  return Array.from(new Set(tokenize(query))).slice(0, 12);
}

export function snippetFor(text: string, terms: string[], width = 240): string {
  if (text.length <= width) return text;
  const lowered = text.toLowerCase();
  let position = -1;
  for (const term of terms) {
    const found = lowered.indexOf(term);
    if (found >= 0 && (position < 0 || found < position)) position = found;
  }
  if (position < 0) return `${text.slice(0, width).trimEnd()}…`;
  const start = Math.max(0, position - Math.floor(width / 3));
  const end = Math.min(text.length, start + width);
  return `${start > 0 ? "…" : ""}${text.slice(start, end).trim()}${end < text.length ? "…" : ""}`;
}

interface IndexedBlock {
  documentId: string;
  documentTitle: string;
  blockId: string;
  blockType: Block["type"];
  text: string;
}

export class BlockSearchIndex {
  private readonly documents = new Map<string, BlockDocument>();
  private readonly postings = new Map<string, Set<string>>();
  private readonly blocks = new Map<string, IndexedBlock>();

  add(document: BlockDocument): number {
    this.remove(document.id);
    this.documents.set(document.id, document);
    let terms = 0;
    for (const block of document.blocks) {
      const key = `${document.id}::${block.id}`;
      const text = blockPlainText(block);
      this.blocks.set(key, {
        documentId: document.id,
        documentTitle: document.title,
        blockId: block.id,
        blockType: block.type,
        text,
      });
      for (const token of new Set(tokenize(text))) {
        const owners = this.postings.get(token) ?? new Set<string>();
        owners.add(key);
        this.postings.set(token, owners);
        terms += 1;
      }
    }
    return terms;
  }

  remove(documentId: string): boolean {
    if (!this.documents.delete(documentId)) return false;
    for (const [key, block] of Array.from(this.blocks.entries())) {
      if (block.documentId !== documentId) continue;
      this.blocks.delete(key);
      for (const owners of this.postings.values()) owners.delete(key);
    }
    for (const [token, owners] of Array.from(this.postings.entries())) {
      if (owners.size === 0) this.postings.delete(token);
    }
    return true;
  }

  replace(document: BlockDocument): number {
    return this.add(document);
  }

  reindex(documents: BlockDocument[]): number {
    this.clear();
    documents.forEach((document) => this.add(document));
    return documents.length;
  }

  clear(): void {
    this.documents.clear();
    this.postings.clear();
    this.blocks.clear();
  }

  get size(): number {
    return this.blocks.size;
  }

  get documentIds(): string[] {
    return Array.from(this.documents.keys()).sort();
  }

  vocabulary(): string[] {
    return Array.from(this.postings.keys()).sort();
  }

  search(
    query: string,
    options: {
      blockTypes?: Block["type"][];
      documentId?: string;
      matchAll?: boolean;
      limit?: number;
      offset?: number;
    } = {},
  ): SearchHit[] {
    const terms = queryTerms(query);
    if (terms.length === 0) return [];
    const matchAll = options.matchAll ?? true;
    const candidates = new Map<string, number>();
    for (const term of terms) {
      for (const key of this.postings.get(term) ?? []) {
        candidates.set(key, (candidates.get(key) ?? 0) + 1);
      }
    }
    const hits: SearchHit[] = [];
    for (const [key, count] of candidates) {
      if (matchAll && count !== terms.length) continue;
      const indexed = this.blocks.get(key);
      if (!indexed) continue;
      if (options.documentId && indexed.documentId !== options.documentId)
        continue;
      if (options.blockTypes && !options.blockTypes.includes(indexed.blockType))
        continue;
      const lowered = indexed.text.toLowerCase();
      let score = 10 * count;
      for (const term of terms) {
        if (lowered === term) score += 3;
        if (lowered.startsWith(term)) score += 2;
      }
      score += Math.min(10, Math.floor(indexed.text.length / 200));
      hits.push({
        documentId: indexed.documentId,
        documentTitle: indexed.documentTitle,
        blockId: indexed.blockId,
        blockType: indexed.blockType,
        score,
        snippet: snippetFor(indexed.text, terms),
        highlights: terms.filter((term) => lowered.includes(term)),
      });
    }
    hits.sort(
      (left, right) =>
        right.score - left.score ||
        left.documentId.localeCompare(right.documentId) ||
        left.blockId.localeCompare(right.blockId),
    );
    const offset = Math.max(0, options.offset ?? 0);
    const limit = Math.max(0, Math.min(options.limit ?? 50, 200));
    return hits.slice(offset, offset + limit);
  }

  facets(): Record<string, number> {
    const result: Record<string, number> = {};
    for (const block of this.blocks.values())
      result[block.blockType] = (result[block.blockType] ?? 0) + 1;
    return result;
  }

  termsFor(documentId: string, blockId: string): string[] {
    const indexed = this.blocks.get(`${documentId}::${blockId}`);
    return indexed ? tokenize(indexed.text) : [];
  }
}

export function buildSearchIndex(documents: BlockDocument[]): BlockSearchIndex {
  const index = new BlockSearchIndex();
  index.reindex(documents);
  return index;
}

export function mergeHits(left: SearchHit[], right: SearchHit[]): SearchHit[] {
  const seen = new Set<string>();
  const result: SearchHit[] = [];
  for (const hit of [...left, ...right]) {
    const key = `${hit.documentId}::${hit.blockId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(hit);
  }
  result.sort(
    (a, b) => b.score - a.score || a.blockId.localeCompare(b.blockId),
  );
  return result;
}

export function hitKey(hit: SearchHit): string {
  return `${hit.documentId}::${hit.blockId}`;
}

export function highlightText(text: string, terms: string[]): string {
  let result = text;
  for (const term of terms) {
    if (!term) continue;
    const pattern = new RegExp(
      `(${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
      "gi",
    );
    result = result.replace(pattern, "<mark>$1</mark>");
  }
  return result;
}
