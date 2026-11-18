import {
  type Block,
  type BlockDocument,
  type BlockPatch,
  type Mention,
  type MentionKind,
  type PatchEntry,
  type SearchHit,
  type ValidationIssue,
  type ValidationReport,
} from "./types";

type Json = Record<string, unknown>;

function isRecord(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function number(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function boolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function booleanList(value: unknown): boolean[] {
  return Array.isArray(value)
    ? value.filter((item): item is boolean => typeof item === "boolean")
    : [];
}

export function mentionFromApi(value: unknown): Mention {
  const record = isRecord(value) ? value : {};
  const kind = text(record.kind);
  const allowed: MentionKind[] = [
    "note",
    "user",
    "target",
    "finding",
    "evidence",
    "tag",
  ];
  return {
    kind: allowed.includes(kind as MentionKind)
      ? (kind as MentionKind)
      : "note",
    target: text(record.target),
    label: text(record.label),
    start: number(record.start),
    end: number(record.end),
    blockId: text(record.block_id),
  };
}

export function blockFromApi(value: unknown): Block {
  const record = isRecord(value) ? value : {};
  const type = text(record.type);
  const allowed = [
    "paragraph",
    "heading",
    "code",
    "quote",
    "list",
    "table",
    "callout",
    "divider",
    "image",
  ];
  const rows = Array.isArray(record.rows)
    ? record.rows.map((row) => stringList(row))
    : [];
  return {
    id: text(record.id),
    type: (allowed.includes(type) ? type : "paragraph") as Block["type"],
    text: text(record.text),
    level: number(record.level, 1),
    language: text(record.language),
    items: stringList(record.items),
    checked: booleanList(record.checked),
    style: (text(record.style) || "bullet") as Block["style"],
    headers: stringList(record.headers),
    rows,
    tone: (text(record.tone) || "info") as Block["tone"],
    alt: text(record.alt),
    source: text(record.source),
    mentions: Array.isArray(record.mentions)
      ? record.mentions.map(mentionFromApi)
      : [],
    attrs: isRecord(record.attrs)
      ? Object.fromEntries(
          Object.entries(record.attrs).map(([key, item]) => [key, text(item)]),
        )
      : {},
  };
}

export function blockToApi(block: Block): Json {
  return {
    id: block.id,
    type: block.type,
    text: block.text,
    level: block.level,
    language: block.language,
    items: block.items,
    checked: block.checked,
    style: block.style,
    headers: block.headers,
    rows: block.rows,
    tone: block.tone,
    alt: block.alt,
    source: block.source,
    mentions: block.mentions.map((mention) => ({
      kind: mention.kind,
      target: mention.target,
      label: mention.label,
      start: mention.start,
      end: mention.end,
      block_id: mention.blockId,
    })),
    attrs: block.attrs,
  };
}

export function documentFromApi(value: unknown): BlockDocument {
  const record = isRecord(value) ? value : {};
  return {
    id: text(record.id),
    title: text(record.title),
    blocks: Array.isArray(record.blocks) ? record.blocks.map(blockFromApi) : [],
    revision: number(record.revision),
    updatedAt: text(record.updated_at),
    tags: stringList(record.tags),
    metadata: isRecord(record.metadata)
      ? Object.fromEntries(
          Object.entries(record.metadata).map(([key, item]) => [
            key,
            text(item),
          ]),
        )
      : {},
  };
}

export function documentToApi(document: BlockDocument): Json {
  return {
    id: document.id,
    title: document.title,
    blocks: document.blocks.map(blockToApi),
    revision: document.revision,
    updated_at: document.updatedAt,
    tags: document.tags,
    metadata: document.metadata,
  };
}

export function patchEntryFromApi(value: unknown): PatchEntry {
  const record = isRecord(value) ? value : {};
  const operation = text(record.operation);
  return {
    operation: (["insert", "update", "delete", "move"].includes(operation)
      ? operation
      : "update") as PatchEntry["operation"],
    blockId: text(record.block_id),
    block: record.block ? blockFromApi(record.block) : null,
    index: typeof record.index === "number" ? record.index : null,
    previousIndex:
      typeof record.previous_index === "number" ? record.previous_index : null,
  };
}

export function patchFromApi(value: unknown): BlockPatch {
  const record = isRecord(value) ? value : {};
  return {
    documentId: text(record.document_id),
    baseRevision: number(record.base_revision),
    entries: Array.isArray(record.entries)
      ? record.entries.map(patchEntryFromApi)
      : [],
    label: text(record.label),
  };
}

export function patchToApi(patch: BlockPatch): Json {
  return {
    document_id: patch.documentId,
    base_revision: patch.baseRevision,
    label: patch.label,
    entries: patch.entries.map((entry) => ({
      operation: entry.operation,
      block_id: entry.blockId,
      block: entry.block ? blockToApi(entry.block) : null,
      index: entry.index ?? null,
      previous_index: entry.previousIndex ?? null,
    })),
  };
}

export function searchHitFromApi(value: unknown): SearchHit {
  const record = isRecord(value) ? value : {};
  const blockType = text(record.block_type);
  return {
    documentId: text(record.document_id),
    documentTitle: text(record.document_title),
    blockId: text(record.block_id),
    blockType: ([
      "paragraph",
      "heading",
      "code",
      "quote",
      "list",
      "table",
      "callout",
      "divider",
      "image",
    ].includes(blockType)
      ? blockType
      : "paragraph") as SearchHit["blockType"],
    score: number(record.score),
    snippet: text(record.snippet),
    highlights: stringList(record.highlights),
  };
}

export function validationReportFromApi(value: unknown): ValidationReport {
  const record = isRecord(value) ? value : {};
  const issues: ValidationIssue[] = Array.isArray(record.issues)
    ? record.issues.map((item) => {
        const issue = isRecord(item) ? item : {};
        const severity = text(issue.severity);
        return {
          severity: (["error", "warning", "info"].includes(severity)
            ? severity
            : "info") as ValidationIssue["severity"],
          code: text(issue.code),
          message: text(issue.message),
          blockId: text(issue.block_id),
          field: text(issue.field),
        };
      })
    : [];
  return {
    target: text(record.target),
    ok: boolean(record.ok, issues.length === 0),
    errors: number(record.errors),
    warnings: number(record.warnings),
    issues,
  };
}

export function routeBodyPatch(patch: BlockPatch): Json {
  return { patch: patchToApi(patch) };
}

export function isEnvelope(value: unknown): value is Json {
  return isRecord(value) && typeof value.ok === "boolean";
}
