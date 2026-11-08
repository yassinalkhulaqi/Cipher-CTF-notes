import { create } from "zustand";
import { api } from "../lib/api";
import {
  DEFAULT_SIDEBAR_WIDTH,
  DEFAULT_SPLIT,
  MAX_SIDEBAR_WIDTH,
  MAX_SPLIT,
  MIN_SIDEBAR_WIDTH,
  MIN_SPLIT,
} from "../lib/constants";
import {
  countNotes,
  expandAncestors,
  indexTree,
  parentForSelection,
} from "../lib/tree";
import type {
  BootData,
  NodeDetail,
  NodeSummary,
  SaveState,
  Theme,
  TreeNode,
  ViewMode,
} from "../lib/types";
import { clamp } from "../lib/utils";

interface AppState {
  boot: BootData | null;
  bootError: string | null;
  loading: boolean;
  tree: TreeNode[];
  nodes: Map<number, TreeNode>;
  expanded: Set<number>;
  selectedId: number | null;
  note: NodeDetail | null;
  draft: string;
  dirty: boolean;
  saveState: SaveState;
  theme: Theme;
  fontSize: number;
  viewMode: ViewMode;
  syncScroll: boolean;
  restoreLastNote: boolean;
  sidebarWidth: number;
  split: number;
  filter: string;
  focusMode: boolean;

  bootApp: () => Promise<void>;
  refreshTree: () => Promise<void>;
  openNote: (id: number, options?: { focus?: boolean }) => Promise<void>;
  closeNote: () => Promise<void>;
  toggleFolder: (id: number) => void;
  setExpanded: (ids: Iterable<number>) => void;
  setDraft: (content: string) => void;
  saveNow: () => Promise<void>;
  renameNode: (id: number, title: string) => Promise<NodeSummary>;
  renameCurrent: (title: string) => Promise<void>;
  updateCurrent: (fields: {
    status: string;
    difficulty: string;
    target: string;
    tags: string;
    flag: string;
  }) => Promise<NodeSummary>;
  togglePin: (id?: number) => Promise<void>;
  createNote: (input: {
    template_key: string;
    title: string;
    target: string;
    parent_id: number | null;
  }) => Promise<NodeSummary>;
  quickNote: () => Promise<NodeSummary>;
  quickCapture: (input: {
    title: string;
    content: string;
    target: string;
    tags: string;
  }) => Promise<NodeSummary>;
  createFolder: (
    title: string,
    parentId: number | null,
  ) => Promise<NodeSummary>;
  duplicateNode: (id: number) => Promise<void>;
  moveNode: (
    id: number,
    parentId: number | null,
    beforeId?: number | null,
  ) => Promise<void>;
  reorderSelected: (offset: number) => Promise<void>;
  trashNode: (id: number) => Promise<number>;
  restoreNode: (id: number) => Promise<void>;
  emptyTrash: () => Promise<number>;
  loadDemo: () => Promise<void>;
  setTheme: (theme: Theme) => void;
  setFontSize: (size: number) => void;
  setViewMode: (mode: ViewMode) => void;
  cycleView: () => void;
  setSyncScroll: (value: boolean) => void;
  setRestoreLastNote: (value: boolean) => void;
  setSidebarWidth: (width: number, persist?: boolean) => void;
  setSplit: (percent: number, persist?: boolean) => void;
  setFilter: (value: string) => void;
  toggleFocusMode: () => void;
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;
let draftRevision = 0;

function clearSaveTimer(): void {
  if (saveTimer !== null) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

function applyFontSize(size: number): void {
  document.documentElement.style.setProperty("--editor-size", `${size}px`);
}

function persist(values: Record<string, string | number>): void {
  void api.setSettings(values).catch(() => {
    /* Settings are best-effort; the UI already reflects the change. */
  });
}

export const useAppStore = create<AppState>()((set, get) => ({
  boot: null,
  bootError: null,
  loading: true,
  tree: [],
  nodes: new Map(),
  expanded: new Set(),
  selectedId: null,
  note: null,
  draft: "",
  dirty: false,
  saveState: "idle",
  theme: "dark",
  fontSize: 13,
  viewMode: "split",
  syncScroll: true,
  restoreLastNote: true,
  sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
  split: DEFAULT_SPLIT,
  filter: "",
  focusMode: false,

  bootApp: async () => {
    set({ loading: true, bootError: null });
    try {
      const boot = await api.boot();
      const theme: Theme = boot.theme === "light" ? "light" : "dark";
      const viewMode: ViewMode = ["editor", "split", "preview"].includes(
        boot.view_mode,
      )
        ? boot.view_mode
        : "split";
      const fontSize = clamp(boot.font_size || 13, 9, 18);
      applyTheme(theme);
      applyFontSize(fontSize);
      set({
        boot,
        theme,
        fontSize,
        viewMode,
        syncScroll: boot.sync_preview_scroll !== false,
        restoreLastNote: boot.restore_last_note !== false,
        sidebarWidth: clamp(
          boot.sidebar_width ?? DEFAULT_SIDEBAR_WIDTH,
          MIN_SIDEBAR_WIDTH,
          MAX_SIDEBAR_WIDTH,
        ),
        split: clamp(boot.split_sash ?? DEFAULT_SPLIT, MIN_SPLIT, MAX_SPLIT),
      });

      const tree = await api.tree();
      const nodes = indexTree(tree);
      const expanded = new Set<number>();
      for (const node of tree) {
        if (node.kind === "folder" && node.children.length > 0)
          expanded.add(node.id);
      }
      set({ tree, nodes, expanded });

      if (boot.restore_last_note && boot.last_note) {
        try {
          await get().openNote(boot.last_note, { focus: false });
        } catch {
          /* The last note may have been deleted; show the dashboard. */
        }
      }
      set({ loading: false });
    } catch (error) {
      set({
        loading: false,
        bootError:
          error instanceof Error ? error.message : "Unable to open the vault",
      });
    }
  },

  refreshTree: async () => {
    const tree = await api.tree();
    set({ tree, nodes: indexTree(tree) });
  },

  openNote: async (id, options) => {
    const current = get().note;
    if (current?.id === id && !options?.focus) return;
    try {
      await get().saveNow();
    } catch {
      throw new Error(
        "Could not save the current note. It is still open; retry saving before switching.",
      );
    }
    const node = await api.node(id);
    if (node.kind === "folder") {
      const expanded = new Set(get().expanded);
      expanded.add(id);
      set({ expanded });
      return;
    }
    const expanded = new Set(get().expanded);
    expandAncestors(get().nodes, id, expanded);
    set({
      selectedId: id,
      note: node,
      draft: node.content ?? "",
      dirty: false,
      saveState: "idle",
      expanded,
    });
    persist({ last_note: String(id) });
  },

  closeNote: async () => {
    try {
      await get().saveNow();
    } catch {
      throw new Error(
        "Could not save the current note. It is still open; retry saving before closing.",
      );
    }
    set({
      selectedId: null,
      note: null,
      draft: "",
      dirty: false,
      saveState: "idle",
    });
  },

  toggleFolder: (id) => {
    const expanded = new Set(get().expanded);
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    set({ expanded });
  },

  setExpanded: (ids) => set({ expanded: new Set(ids) }),

  setDraft: (content) => {
    if (!get().note) return;
    draftRevision += 1;
    set({ draft: content, dirty: true, saveState: "dirty" });
    clearSaveTimer();
    saveTimer = setTimeout(() => {
      void get()
        .saveNow()
        .catch(() => undefined);
    }, 850);
  },

  saveNow: async () => {
    const { note, draft, dirty } = get();
    if (!note || !dirty) return;
    clearSaveTimer();
    const revision = draftRevision;
    const noteId = note.id;
    const content = draft;
    set({ saveState: "saving" });
    try {
      const updated = await api.saveContent(noteId, content);
      if (get().note?.id !== noteId) return;
      if (draftRevision === revision) {
        set((state) => ({
          note: state.note
            ? {
                ...state.note,
                content,
                updated_at: updated.updated_at,
                path: updated.path,
                title: updated.title,
              }
            : state.note,
          dirty: false,
          saveState: "saved",
        }));
      } else {
        set({ saveState: "dirty" });
      }
    } catch (error) {
      set({ saveState: "error" });
      throw error;
    }
  },

  renameNode: async (id, title) => {
    const clean = title.trim() || "Untitled";
    const updated = await api.rename(id, clean);
    await get().refreshTree();
    set((state) => ({
      note:
        state.note && state.note.id === id
          ? { ...state.note, title: updated.title, path: updated.path }
          : state.note,
    }));
    return updated;
  },

  renameCurrent: async (title) => {
    const note = get().note;
    if (!note) return;
    await get().renameNode(note.id, title);
  },

  updateCurrent: async (fields) => {
    const note = get().note;
    if (!note) throw new Error("No note is open");
    await get().saveNow();
    const updated = await api.updateNode({ id: note.id, ...fields });
    await get().refreshTree();
    set((state) => ({
      note: state.note
        ? {
            ...state.note,
            status: updated.status,
            difficulty: updated.difficulty,
            target: updated.target,
            tags: updated.tags,
            tag_list: updated.tag_list,
            flag: updated.flag,
            title: updated.title,
            path: updated.path,
            pinned: updated.pinned,
          }
        : state.note,
    }));
    return updated;
  },

  togglePin: async (id) => {
    const target = id ?? get().note?.id;
    if (target === undefined) return;
    const node = get().nodes.get(target);
    if (!node) return;
    const updated = await api.setPinned(target, !node.pinned);
    await get().refreshTree();
    set((state) => ({
      note:
        state.note && state.note.id === target
          ? { ...state.note, pinned: updated.pinned }
          : state.note,
    }));
  },

  createNote: async (input) => {
    try {
      await get().saveNow();
    } catch {
      throw new Error(
        "Could not save the current note. It is still open; retry saving before creating another.",
      );
    }
    const node = await api.createNote(input);
    const expanded = new Set(get().expanded);
    if (node.parent_id !== null) expanded.add(node.parent_id);
    set({ expanded });
    await get().refreshTree();
    await get().openNote(node.id);
    return node;
  },

  quickNote: async () => {
    const [settings, templates, state] = await Promise.all([
      api.getSettings(),
      api.templates(),
      Promise.resolve(get()),
    ]);
    const keys = new Set(templates.map((template) => template.key));
    const templateKey = keys.has(settings.last_template)
      ? settings.last_template
      : "ctf";
    const parentId = parentForSelection(state.nodes, state.selectedId);
    return get().createNote({
      template_key: templateKey,
      title: "",
      target: state.note?.target ?? "",
      parent_id: parentId,
    });
  },

  quickCapture: async (input) => {
    try {
      await get().saveNow();
    } catch {
      throw new Error(
        "Could not save the current note. It is still open; retry saving before capturing.",
      );
    }
    const node = await api.quickCapture(input);
    await get().refreshTree();
    await get().openNote(node.id);
    return node;
  },

  createFolder: async (title, parentId) => {
    const node = await api.createFolder({ title, parent_id: parentId });
    const expanded = new Set(get().expanded);
    if (node.parent_id !== null) expanded.add(node.parent_id);
    expanded.add(node.id);
    set({ expanded });
    await get().refreshTree();
    return node;
  },

  duplicateNode: async (id) => {
    await api.duplicateNode(id);
    await get().refreshTree();
  },

  moveNode: async (id, parentId, beforeId = null) => {
    await api.moveNode(id, parentId, beforeId);
    const expanded = new Set(get().expanded);
    if (parentId !== null) expanded.add(parentId);
    set({ expanded });
    await get().refreshTree();
    if (get().note?.id === id) {
      await get().openNote(id, { focus: false });
    }
  },

  reorderSelected: async (offset) => {
    const id = get().selectedId;
    if (id === null) return;
    await api.reorderNode(id, offset);
    await get().refreshTree();
  },

  trashNode: async (id) => {
    if (get().note?.id === id) {
      try {
        await get().saveNow();
      } catch {
        throw new Error(
          "Could not save the current note. Retry saving before moving it to the trash.",
        );
      }
    }
    const result = await api.trashNode(id);
    if (get().note?.id === id) {
      clearSaveTimer();
      set({
        note: null,
        draft: "",
        selectedId: null,
        dirty: false,
        saveState: "idle",
      });
    }
    await get().refreshTree();
    return result.removed;
  },

  restoreNode: async (id) => {
    await api.restoreNode(id);
    await get().refreshTree();
  },

  emptyTrash: async () => {
    const result = await api.emptyTrash();
    await get().refreshTree();
    return result.removed;
  },

  loadDemo: async () => {
    await api.loadDemo();
    await get().refreshTree();
    const state = get();
    const first = state.tree.find((node) => node.kind === "note");
    if (first) await get().openNote(first.id, { focus: false });
  },

  setTheme: (theme) => {
    applyTheme(theme);
    set({ theme });
    persist({ theme });
  },

  setFontSize: (size) => {
    const next = clamp(size, 9, 18);
    applyFontSize(next);
    set({ fontSize: next });
    persist({ font_size: next });
  },

  setViewMode: (mode) => {
    set({ viewMode: mode });
    persist({ view_mode: mode });
  },

  cycleView: () => {
    const order: ViewMode[] = ["editor", "split", "preview"];
    const current = order.indexOf(get().viewMode);
    get().setViewMode(order[(current + 1) % order.length] ?? "split");
  },

  setSyncScroll: (value) => {
    set({ syncScroll: value });
    persist({ sync_preview_scroll: value ? "1" : "0" });
  },

  setRestoreLastNote: (value) => {
    set({ restoreLastNote: value });
    persist({ restore_last_note: value ? "1" : "0" });
  },

  setSidebarWidth: (width, persistWidth = false) => {
    const next = clamp(width, MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH);
    set({ sidebarWidth: next });
    if (persistWidth) persist({ sidebar_width: Math.round(next) });
  },

  setSplit: (percent, persistSplit = false) => {
    const next = clamp(percent, MIN_SPLIT, MAX_SPLIT);
    set({ split: next });
    if (persistSplit) persist({ split_sash: Math.round(next) });
  },

  setFilter: (value) => set({ filter: value }),

  toggleFocusMode: () => set((state) => ({ focusMode: !state.focusMode })),
}));

export function noteCount(tree: TreeNode[]): number {
  return countNotes(tree);
}
