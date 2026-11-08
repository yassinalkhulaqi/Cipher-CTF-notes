import type {
  BootData,
  ExportPayload,
  FlagHit,
  FlagInsights,
  FlagPattern,
  NodeDetail,
  NodeSummary,
  SearchHit,
  Settings,
  Snippet,
  TagCount,
  Template,
  TrashedNode,
  TreeNode,
  VaultGraph,
  VaultStats,
  Attachment,
} from "./types";

type Envelope<T> = { ok: true; data: T } | { ok: false; error?: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status = 0,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function call<T>(
  method: string,
  body: Record<string, unknown> = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Cannot reach the RedScribe backend", 0);
  }
  let payload: Envelope<T> | null = null;
  try {
    payload = (await response.json()) as Envelope<T>;
  } catch {
    payload = null;
  }
  if (!response.ok || !payload || payload.ok !== true) {
    const message =
      payload && payload.ok === false && payload.error
        ? payload.error
        : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return payload.data;
}

export const api = {
  boot: () => call<BootData>("boot"),
  tree: () => call<TreeNode[]>("tree"),
  node: (id: number) => call<NodeDetail>("node", { id }),
  createNote: (body: {
    template_key: string;
    title: string;
    target: string;
    parent_id: number | null;
  }) => call<NodeSummary>("create_note", body),
  createFolder: (body: { title: string; parent_id: number | null }) =>
    call<NodeSummary>("create_folder", body),
  rename: (id: number, title: string) =>
    call<NodeSummary>("rename", { id, title }),
  updateNode: (body: {
    id: number;
    title?: string;
    tags?: string;
    target?: string;
    status?: string;
    difficulty?: string;
    flag?: string;
    pinned?: boolean;
  }) => call<NodeSummary>("update_node", body),
  saveContent: (id: number, content: string) =>
    call<NodeSummary>("save_content", { id, content }),
  setPinned: (id: number, pinned: boolean) =>
    call<NodeSummary>("set_pinned", { id, pinned }),
  duplicateNode: (id: number) => call<NodeSummary>("duplicate_node", { id }),
  reorderNode: (id: number, offset: number) =>
    call<NodeSummary | null>("reorder_node", { id, offset }),
  moveNode: (
    id: number,
    parentId: number | null,
    beforeId: number | null = null,
  ) =>
    call<NodeSummary>("move_node", {
      id,
      parent_id: parentId,
      before_id: beforeId,
    }),
  trashNode: (id: number) => call<{ removed: number }>("trash_node", { id }),
  restoreNode: (id: number) => call<NodeSummary>("restore_node", { id }),
  trashedNodes: () => call<TrashedNode[]>("trashed_nodes"),
  emptyTrash: () => call<{ removed: number }>("empty_trash"),
  search: (query: string) => call<SearchHit[]>("search", { query }),
  quickJump: (query: string) => call<NodeSummary[]>("quick_jump", { query }),
  recentNotes: (limit = 10) => call<NodeSummary[]>("recent_notes", { limit }),
  pinnedNotes: () => call<NodeSummary[]>("pinned_notes"),
  stats: () => call<VaultStats>("stats"),
  collectedFlags: () => call<FlagHit[]>("collected_flags"),
  tagCounts: () => call<TagCount[]>("tag_counts"),
  notesTagged: (tag: string) => call<NodeSummary[]>("notes_tagged", { tag }),
  templates: () => call<Template[]>("templates"),
  listSnippets: () => call<Snippet[]>("list_snippets"),
  searchSnippets: (query: string) =>
    call<Snippet[]>("search_snippets", { query }),
  resolveSnippet: (command: string, target: string) =>
    call<{ command: string }>("resolve_snippet", { command, target }),
  createSnippet: (body: {
    title: string;
    command: string;
    description: string;
    tags: string;
  }) => call<Snippet>("create_snippet", body),
  updateSnippet: (body: {
    id: number;
    title: string;
    command: string;
    description: string;
    tags: string;
  }) => call<Snippet>("update_snippet", body),
  deleteSnippet: (id: number) =>
    call<{ removed: number }>("delete_snippet", { id }),
  renderPreview: (content: string) =>
    call<{ html: string }>("render_preview", { content }),
  getSettings: () => call<Settings>("get_settings"),
  setSettings: (values: Record<string, string | number>) =>
    call<Settings>("set_settings", values),
  loadDemo: () => call<{ ok: boolean }>("load_demo"),
  exportNoteMarkdown: (id: number) =>
    call<ExportPayload>("export_note_markdown", { id }),
  exportNoteHtml: (id: number) =>
    call<ExportPayload>("export_note_html", { id }),
  exportVaultHtml: () => call<ExportPayload>("export_vault_html"),
  graph: () => call<VaultGraph>("graph"),
  flagPatterns: () => call<FlagPattern[]>("flag_patterns"),
  flagInsights: () => call<FlagInsights>("flag_insights"),
  attachments: () => call<Attachment[]>("attachments"),
  attachment: (body: { id: number }) => call<Attachment>("attachment", body),
  quickCapture: (body: {
    title: string;
    content: string;
    target: string;
    tags: string;
  }) => call<NodeSummary>("quick_capture", body),
};

export function downloadNote(id: number, format: "md" | "html"): void {
  const anchor = document.createElement("a");
  anchor.href = `/download/note/${id}/${format}`;
  anchor.download = "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function downloadVault(): void {
  const anchor = document.createElement("a");
  anchor.href = "/download/vault/html";
  anchor.download = "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
