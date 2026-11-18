export const BLOCK_TYPES = [
  "paragraph",
  "heading",
  "code",
  "quote",
  "list",
  "table",
  "callout",
  "divider",
  "image",
] as const;

export type BlockType = (typeof BLOCK_TYPES)[number];

export const LIST_STYLES = ["bullet", "ordered", "tasks"] as const;
export type ListStyle = (typeof LIST_STYLES)[number];

export const CALLOUT_TONES = [
  "info",
  "warning",
  "success",
  "danger",
  "note",
  "tip",
] as const;
export type CalloutTone = (typeof CALLOUT_TONES)[number];

export const MENTION_KINDS = [
  "note",
  "user",
  "target",
  "finding",
  "evidence",
  "tag",
] as const;
export type MentionKind = (typeof MENTION_KINDS)[number];

export const PATCH_OPERATIONS = ["insert", "update", "delete", "move"] as const;
export type PatchOperation = (typeof PATCH_OPERATIONS)[number];

export const DIFF_OPERATIONS = ["add", "remove", "replace", "move"] as const;
export type DiffOperation = (typeof DIFF_OPERATIONS)[number];

export const ISSUE_SEVERITIES = ["error", "warning", "info"] as const;
export type IssueSeverity = (typeof ISSUE_SEVERITIES)[number];

export interface Mention {
  kind: MentionKind;
  target: string;
  label: string;
  start: number;
  end: number;
  blockId: string;
}

export interface Block {
  id: string;
  type: BlockType;
  text: string;
  level: number;
  language: string;
  items: string[];
  checked: boolean[];
  style: ListStyle;
  headers: string[];
  rows: string[][];
  tone: CalloutTone;
  alt: string;
  source: string;
  mentions: Mention[];
  attrs: Record<string, string>;
}

export interface BlockDocument {
  id: string;
  title: string;
  blocks: Block[];
  revision: number;
  updatedAt: string;
  tags: string[];
  metadata: Record<string, string>;
}

export interface PatchEntry {
  operation: PatchOperation;
  blockId: string;
  block?: Block | null;
  index?: number | null;
  previousIndex?: number | null;
}

export interface BlockPatch {
  documentId: string;
  baseRevision: number;
  entries: PatchEntry[];
  label: string;
}

export interface DiffEntry {
  operation: DiffOperation;
  blockId: string;
  index: number;
  previousIndex: number | null;
  block: Block | null;
  description: string;
}

export interface DocumentDiff {
  leftId: string;
  rightId: string;
  leftRevision: number;
  rightRevision: number;
  entries: DiffEntry[];
}

export interface ValidationIssue {
  severity: IssueSeverity;
  code: string;
  message: string;
  blockId: string;
  field: string;
}

export interface ValidationReport {
  target: string;
  ok: boolean;
  errors: number;
  warnings: number;
  issues: ValidationIssue[];
}

export interface SelectionPoint {
  blockId: string;
  offset: number;
}

export interface SelectionRange {
  anchor: SelectionPoint;
  focus: SelectionPoint;
}

export interface AutosaveBatch {
  documentId: string;
  baseRevision: number;
  entries: PatchEntry[];
  mergedFrom: number;
  firstAtMs: number;
  lastAtMs: number;
  token: string;
  label: string;
}

export interface AutosaveStatus {
  pending: number;
  documentIds: string[];
  operations: number;
  mergedEdits: number;
  nextFlushMs: number;
  intervalMs: number;
  maxWaitMs: number;
}

export interface SearchHit {
  documentId: string;
  documentTitle: string;
  blockId: string;
  blockType: BlockType;
  score: number;
  snippet: string;
  highlights: string[];
}

export interface MentionSuggestion {
  kind: MentionKind;
  target: string;
  label: string;
  score: number;
}

export interface SlashCommand {
  id: string;
  title: string;
  description: string;
  blockType: BlockType;
  keywords: string[];
  group: string;
}

export interface EditorState {
  document: BlockDocument;
  selection: SelectionRange;
  focusedBlockId: string;
  slashQuery: string | null;
  mentionQuery: string | null;
  history: BlockDocument[];
  future: BlockDocument[];
}

export interface KeyboardAction {
  kind:
    | "none"
    | "split"
    | "merge"
    | "delete-block"
    | "move-up"
    | "move-down"
    | "undo"
    | "redo"
    | "format"
    | "duplicate"
    | "open-slash"
    | "close-slash"
    | "accept-slash"
    | "accept-mention"
    | "indent"
    | "outdent";
  payload?: string;
}

export const BLOCK_LIMITS = {
  maxBlocks: 2000,
  maxTextLength: 20000,
  maxItemLength: 2000,
  maxItems: 500,
  maxTableColumns: 24,
  maxTableRows: 500,
  maxHeadingLevel: 6,
  maxPatchOps: 1000,
  autosaveIntervalMs: 800,
  autosaveMaxWaitMs: 4000,
} as const;

export const EMPTY_BLOCK_TYPE: BlockType = "paragraph";
export const DEFAULT_DOCUMENT_TITLE = "Untitled block note";

export function isBlockType(value: string): value is BlockType {
  return (BLOCK_TYPES as readonly string[]).includes(value);
}

export function isMentionKind(value: string): value is MentionKind {
  return (MENTION_KINDS as readonly string[]).includes(value);
}

export function isPatchOperation(value: string): value is PatchOperation {
  return (PATCH_OPERATIONS as readonly string[]).includes(value);
}

export function isCalloutTone(value: string): value is CalloutTone {
  return (CALLOUT_TONES as readonly string[]).includes(value);
}

export function isListStyle(value: string): value is ListStyle {
  return (LIST_STYLES as readonly string[]).includes(value);
}
