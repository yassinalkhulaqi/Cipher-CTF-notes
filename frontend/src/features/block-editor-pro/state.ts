/** State model and reducer for the v4 professional block editor. */

export type BlockKind =
  | "paragraph"
  | "heading"
  | "code"
  | "list"
  | "quote"
  | "table"
  | "divider";

export type InlineMark = "bold" | "italic" | "code" | "link";

export type DeltaKind = "add" | "remove" | "replace" | "move";

export interface ProBlock {
  id: string;
  kind: BlockKind;
  text: string;
  level: number;
  language: string;
  items: string[];
  attrs: Record<string, string>;
}

export interface ProDocument {
  id: string;
  title: string;
  blocks: ProBlock[];
}

export interface Delta {
  id: string;
  kind: DeltaKind;
  text: string;
  leftIndex: number;
  rightIndex: number;
}

export interface SnapshotMeta {
  id: string;
  revision: number;
  reason: string;
  checksum: string;
  created_at: string;
}

export interface EditPayload {
  op: "insert" | "update" | "delete" | "move";
  block_id: string;
  index: number;
  target_index?: number | null;
  block?: ProBlock | null;
  note?: string;
}

export type EditorStatus = "idle" | "saving" | "saved" | "error";

export interface EditorState {
  document: ProDocument;
  selectedId: string;
  focusMode: boolean;
  slashOpen: boolean;
  findOpen: boolean;
  diffOpen: boolean;
  find: string;
  replace: string;
  dirty: boolean;
  revision: number;
  snapshots: SnapshotMeta[];
  deltas: Delta[];
  status: EditorStatus;
  error: string;
}

export type EditorAction =
  | { type: "load"; document: ProDocument; revision?: number }
  | { type: "select"; id: string }
  | { type: "set-title"; title: string }
  | { type: "update-block"; id: string; patch: Partial<ProBlock> }
  | { type: "insert"; block: ProBlock; index?: number }
  | { type: "delete"; id: string }
  | { type: "move"; id: string; target: number }
  | { type: "set-slash"; open: boolean }
  | { type: "set-find"; open: boolean }
  | { type: "set-diff"; open: boolean }
  | { type: "find"; value: string }
  | { type: "replace"; value: string }
  | { type: "replace-all" }
  | { type: "toggle-focus" }
  | { type: "mark-dirty" }
  | { type: "saving" }
  | { type: "saved"; revision: number }
  | { type: "error"; message: string }
  | { type: "snapshots"; snapshots: SnapshotMeta[] }
  | { type: "diff"; deltas: Delta[] };

export const SLASH_BLOCK_KINDS: readonly BlockKind[] = [
  "paragraph",
  "heading",
  "list",
  "code",
  "quote",
  "table",
  "divider",
];

export const BLOCK_LABELS: Readonly<Record<BlockKind, string>> = {
  paragraph: "Paragraph",
  heading: "Heading",
  code: "Code",
  list: "List",
  quote: "Quote",
  table: "Table",
  divider: "Divider",
};

export const INLINE_MARKS: readonly InlineMark[] = [
  "bold",
  "italic",
  "code",
  "link",
];

export function emptyDocument(id = "draft"): ProDocument {
  return { id, title: "Untitled", blocks: [] };
}

export function createBlock(
  id: string,
  kind: BlockKind = "paragraph",
  text = "",
): ProBlock {
  return {
    id,
    kind,
    text,
    level: kind === "heading" ? 2 : 1,
    language: kind === "code" ? "text" : "",
    items: [],
    attrs:
      kind === "list"
        ? { style: "bullet" }
        : kind === "table"
          ? { header: "A|B" }
          : {},
  };
}

export function createInitialState(
  document: ProDocument = emptyDocument(),
  revision = 0,
): EditorState {
  return {
    document,
    selectedId: document.blocks[0]?.id ?? "",
    focusMode: false,
    slashOpen: false,
    findOpen: false,
    diffOpen: false,
    find: "",
    replace: "",
    dirty: false,
    revision,
    snapshots: [],
    deltas: [],
    status: "idle",
    error: "",
  };
}

function updateBlock(
  document: ProDocument,
  id: string,
  patch: Partial<ProBlock>,
): ProDocument {
  return {
    ...document,
    blocks: document.blocks.map((block) =>
      block.id === id ? { ...block, ...patch } : block,
    ),
  };
}

function replaceAll(
  document: ProDocument,
  needle: string,
  replacement: string,
): ProDocument {
  const value = needle.trim();
  if (!value) return document;
  const swap = (text: string): string => {
    if (!text.toLowerCase().includes(value.toLowerCase())) return text;
    let result = text;
    let cursor = 0;
    while (cursor < result.length) {
      const index = result.toLowerCase().indexOf(value.toLowerCase(), cursor);
      if (index < 0) break;
      result =
        result.slice(0, index) +
        replacement +
        result.slice(index + value.length);
      cursor = index + Math.max(replacement.length, 1);
    }
    return result;
  };
  return {
    ...document,
    title: swap(document.title),
    blocks: document.blocks.map((block) => ({
      ...block,
      text: swap(block.text),
      items: block.items.map(swap),
    })),
  };
}

export function editorReducer(
  state: EditorState,
  action: EditorAction,
): EditorState {
  switch (action.type) {
    case "load":
      return {
        ...state,
        document: action.document,
        revision: action.revision ?? state.revision,
        selectedId: action.document.blocks[0]?.id ?? "",
        dirty: false,
        status: "idle",
        error: "",
      };
    case "select":
      return { ...state, selectedId: action.id, slashOpen: false };
    case "set-title":
      return {
        ...state,
        document: { ...state.document, title: action.title },
        dirty: true,
      };
    case "update-block":
      return {
        ...state,
        document: updateBlock(state.document, action.id, action.patch),
        dirty: true,
        status: "idle",
      };
    case "insert": {
      const blocks = [...state.document.blocks];
      const index = Math.max(
        0,
        Math.min(action.index ?? blocks.length, blocks.length),
      );
      blocks.splice(index, 0, action.block);
      return {
        ...state,
        document: { ...state.document, blocks },
        selectedId: action.block.id,
        slashOpen: false,
        dirty: true,
      };
    }
    case "delete": {
      const removed = state.document.blocks.find(
        (block) => block.id === action.id,
      );
      const blocks = state.document.blocks.filter(
        (block) => block.id !== action.id,
      );
      return {
        ...state,
        document: { ...state.document, blocks },
        selectedId:
          state.selectedId === action.id
            ? (blocks[0]?.id ?? "")
            : state.selectedId,
        dirty: state.dirty || removed !== undefined,
      };
    }
    case "move": {
      const blocks = [...state.document.blocks];
      const source = blocks.findIndex((block) => block.id === action.id);
      if (source < 0) return state;
      const [moved] = blocks.splice(source, 1);
      const target = Math.max(0, Math.min(action.target, blocks.length));
      blocks.splice(target, 0, moved);
      return { ...state, document: { ...state.document, blocks }, dirty: true };
    }
    case "set-slash":
      return { ...state, slashOpen: action.open };
    case "set-find":
      return { ...state, findOpen: action.open };
    case "set-diff":
      return { ...state, diffOpen: action.open };
    case "find":
      return { ...state, find: action.value };
    case "replace":
      return { ...state, replace: action.value };
    case "replace-all":
      return {
        ...state,
        document: replaceAll(state.document, state.find, state.replace),
        dirty: state.dirty || state.find.trim().length > 0,
      };
    case "toggle-focus":
      return {
        ...state,
        focusMode: !state.focusMode,
        slashOpen: false,
        findOpen: false,
      };
    case "mark-dirty":
      return { ...state, dirty: true };
    case "saving":
      return { ...state, status: "saving", error: "" };
    case "saved":
      return {
        ...state,
        status: "saved",
        dirty: false,
        revision: action.revision,
        error: "",
      };
    case "error":
      return { ...state, status: "error", error: action.message };
    case "snapshots":
      return { ...state, snapshots: [...action.snapshots] };
    case "diff":
      return { ...state, deltas: [...action.deltas] };
  }
}

export function findMatches(document: ProDocument, needle: string): string[] {
  const value = needle.trim().toLowerCase();
  if (!value) return [];
  const matches: string[] = [];
  if (document.title.toLowerCase().includes(value)) matches.push("title");
  for (const block of document.blocks) {
    if (
      block.text.toLowerCase().includes(value) ||
      block.items.some((item) => item.toLowerCase().includes(value))
    ) {
      matches.push(block.id);
    }
  }
  return matches;
}

export function countWords(document: ProDocument): number {
  const text = [
    document.title,
    ...document.blocks.flatMap((block) => [block.text, ...block.items]),
  ];
  return text.reduce(
    (total, value) => total + value.trim().split(/\s+/).filter(Boolean).length,
    0,
  );
}

export function checksum(document: ProDocument): string {
  const raw = JSON.stringify(document);
  let hash = 5381;
  for (let index = 0; index < raw.length; index += 1) {
    hash = ((hash << 5) + hash + raw.charCodeAt(index)) | 0;
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function diffDeltas(before: ProDocument, after: ProDocument): Delta[] {
  const deltas: Delta[] = [];
  const previous = new Map(
    before.blocks.map((block, index) => [block.id, { block, index }]),
  );
  const next = new Map(
    after.blocks.map((block, index) => [block.id, { block, index }]),
  );
  for (const block of before.blocks) {
    if (!next.has(block.id)) {
      deltas.push({
        id: block.id,
        kind: "remove",
        text: block.text,
        leftIndex: previous.get(block.id)?.index ?? -1,
        rightIndex: -1,
      });
    }
  }
  after.blocks.forEach((block, index) => {
    const prior = previous.get(block.id);
    if (!prior) {
      deltas.push({
        id: block.id,
        kind: "add",
        text: block.text,
        leftIndex: -1,
        rightIndex: index,
      });
    } else if (
      prior.block.text !== block.text ||
      prior.block.kind !== block.kind
    ) {
      deltas.push({
        id: block.id,
        kind: "replace",
        text: block.text,
        leftIndex: prior.index,
        rightIndex: index,
      });
    } else if (prior.index !== index) {
      deltas.push({
        id: block.id,
        kind: "move",
        text: block.text,
        leftIndex: prior.index,
        rightIndex: index,
      });
    }
  });
  return deltas;
}

export function blockLabel(block: ProBlock): string {
  if (block.kind === "heading") return `H${block.level}`;
  if (block.kind === "code") return block.language || "code";
  if (block.kind === "list") return `list · ${block.attrs.style ?? "bullet"}`;
  return BLOCK_LABELS[block.kind];
}

export function applyInlineMark(
  block: ProBlock,
  mark: InlineMark,
  target: string,
  href = "",
): ProBlock {
  if (!target || !block.text.includes(target)) return block;
  let wrapped: string;
  if (mark === "bold") wrapped = `**${target}**`;
  else if (mark === "italic") wrapped = `*${target}*`;
  else if (mark === "code") wrapped = `\`${target}\``;
  else if (!href.trim()) return block;
  else wrapped = `[${target}](${href.trim()})`;
  return { ...block, text: block.text.replace(target, wrapped) };
}
