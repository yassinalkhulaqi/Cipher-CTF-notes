/** Small UI store; history is sanitized and bounded by pure helpers. */

import { create } from "zustand";
import { MAX_HISTORY, pushEntry, validateManifest } from "./pure";
import type {
  ConsoleEntry,
  ExplorerRequest,
  ExplorerResponse,
  ExplorerTab,
  ValidationReport,
} from "./types";

export const DEFAULT_REQUEST: ExplorerRequest = {
  namespace: "extensions",
  action: "list",
  bodyText: '{\n  "offset": 0,\n  "size": 20\n}',
  capability: "",
  etag: "",
  idempotencyKey: "",
  allowWrite: false,
};

export interface ApiExplorerState {
  tab: ExplorerTab;
  request: ExplorerRequest;
  response: ExplorerResponse | null;
  history: ConsoleEntry[];
  manifestText: string;
  report: ValidationReport | null;
  busy: boolean;
  error: string | null;
  setTab: (tab: ExplorerTab) => void;
  patchRequest: (patch: Partial<ExplorerRequest>) => void;
  resetRequest: () => void;
  setResponse: (response: ExplorerResponse | null) => void;
  setManifestText: (text: string) => void;
  validateLocal: () => ValidationReport;
  setReport: (report: ValidationReport | null) => void;
  appendEntry: (entry: ConsoleEntry) => void;
  clearHistory: () => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
}

export const useApiExplorerStore = create<ApiExplorerState>((set, get) => ({
  tab: "explorer",
  request: { ...DEFAULT_REQUEST },
  response: null,
  history: [],
  manifestText: "",
  report: null,
  busy: false,
  error: null,

  setTab: (tab) => set({ tab }),
  patchRequest: (patch) =>
    set((state) => ({ request: { ...state.request, ...patch } })),
  resetRequest: () => set({ request: { ...DEFAULT_REQUEST }, response: null }),
  setResponse: (response) => set({ response }),
  setManifestText: (manifestText) => set({ manifestText }),
  validateLocal: () => {
    const text = get().manifestText;
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      const report: ValidationReport = {
        valid: false,
        issues: [
          {
            path: "manifest",
            code: "invalid_json",
            message: "Manifest text is not valid JSON",
            severity: "error",
          },
        ],
        fingerprint: "",
      };
      set({ report });
      return report;
    }
    const report = validateManifest(parsed);
    set({ report });
    return report;
  },
  setReport: (report) => set({ report }),
  appendEntry: (entry) =>
    set((state) => ({ history: pushEntry(state.history, entry, MAX_HISTORY) })),
  clearHistory: () => set({ history: [] }),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error }),
}));
