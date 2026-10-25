import { create } from "zustand";

export type ModalName =
  | "palette"
  | "search"
  | "snippets"
  | "snippet-form"
  | "new-note"
  | "new-folder"
  | "properties"
  | "trash"
  | "dashboard"
  | "settings"
  | "help"
  | "confirm"
  | null;

export type FindMode = "find" | "replace";

export interface ToastItem {
  id: number;
  message: string;
  tone: "default" | "success" | "error";
}

export interface ConfirmRequest {
  title: string;
  message: string;
  confirmLabel: string;
  danger: boolean;
  action: () => void | Promise<void>;
}

interface UiState {
  modal: ModalName;
  modalStack: ModalName[];
  newNoteParent: number | null | undefined;
  newNoteTemplate: string | null | undefined;
  newFolderParent: number | null | undefined;
  snippetEditorId: number | null;
  toasts: ToastItem[];
  confirmRequest: ConfirmRequest | null;
  mobileSidebarOpen: boolean;
  findMode: FindMode | null;
  cursorLine: number;
  cursorColumn: number;

  openModal: (modal: Exclude<ModalName, null>) => void;
  closeModal: () => void;
  closeAllModals: () => void;
  openNewNote: (
    parentId?: number | null,
    templateKey?: string | null,
  ) => void;
  openNewFolder: (parentId?: number | null) => void;
  openSnippetForm: (id: number | null) => void;
  askConfirm: (request: ConfirmRequest) => void;
  resolveConfirm: () => void;
  toast: (message: string, tone?: ToastItem["tone"]) => void;
  dismissToast: (id: number) => void;
  setMobileSidebar: (open: boolean) => void;
  openFind: (mode?: FindMode) => void;
  closeFind: () => void;
  setCursorPosition: (line: number, column: number) => void;
}

let toastId = 0;

export const useUiStore = create<UiState>()((set, get) => ({
  modal: null,
  modalStack: [],
  newNoteParent: undefined,
  newNoteTemplate: undefined,
  newFolderParent: undefined,
  snippetEditorId: null,
  toasts: [],
  confirmRequest: null,
  mobileSidebarOpen: false,
  findMode: null,
  cursorLine: 1,
  cursorColumn: 1,

  openModal: (modal) => {
    const stack = get().modalStack.filter((item) => item !== modal);
    stack.push(modal);
    set({ modal, modalStack: stack });
  },

  closeModal: () => {
    const stack = [...get().modalStack];
    stack.pop();
    set({
      modal: stack[stack.length - 1] ?? null,
      modalStack: stack,
      confirmRequest: stack.includes("confirm") ? get().confirmRequest : null,
    });
  },

  closeAllModals: () =>
    set({ modal: null, modalStack: [], confirmRequest: null }),

  openNewNote: (parentId, templateKey) => {
    set({ newNoteParent: parentId, newNoteTemplate: templateKey });
    get().openModal("new-note");
  },

  openNewFolder: (parentId) => {
    set({ newFolderParent: parentId });
    get().openModal("new-folder");
  },

  openSnippetForm: (id) => {
    set({ snippetEditorId: id });
    get().openModal("snippet-form");
  },

  askConfirm: (request) => {
    set({ confirmRequest: request });
    get().openModal("confirm");
  },

  resolveConfirm: () => {
    const request = get().confirmRequest;
    get().closeModal();
    set({ confirmRequest: null });
    if (request) void request.action();
  },

  toast: (message, tone = "default") => {
    toastId += 1;
    const item: ToastItem = { id: toastId, message, tone };
    set((state) => ({ toasts: [...state.toasts.slice(-3), item] }));
    setTimeout(() => {
      get().dismissToast(item.id);
    }, 3200);
  },

  dismissToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    }));
  },

  setMobileSidebar: (open) => set({ mobileSidebarOpen: open }),

  openFind: (mode = "find") => set({ findMode: mode }),

  closeFind: () => set({ findMode: null }),

  setCursorPosition: (line, column) =>
    set({ cursorLine: line, cursorColumn: column }),
}));
