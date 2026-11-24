/** Reducer and selectors for the evidence lab workbench. */

import { dedupeIngest, updateIngestItem } from "./ingestModel";
import { markSelection, selectionBounds } from "./hexModel";
import type {
  BundleDiffData,
  CustodyGraphData,
  EvidenceReportData,
  HexWindowData,
  IngestItem,
  LabManifest,
} from "./types";

export type LabTab = "hex" | "strings" | "entropy";

export interface LabNotice {
  id: number;
  tone: "info" | "good" | "warn" | "bad";
  message: string;
}

export interface LabState {
  manifest: LabManifest | null;
  report: EvidenceReportData | null;
  window: HexWindowData | null;
  graph: CustodyGraphData | null;
  diff: BundleDiffData | null;
  ingest: IngestItem[];
  tab: LabTab;
  stringQuery: string;
  stringKind: string;
  offsetInput: string;
  bytesPerRow: number;
  selectionAnchor: number | null;
  selectionHead: number | null;
  dragging: boolean;
  loading: boolean;
  error: string;
  notices: LabNotice[];
  noticeSequence: number;
}

export type LabAction =
  | { type: "manifest"; manifest: LabManifest }
  | { type: "loading" }
  | { type: "report"; report: EvidenceReportData }
  | { type: "window"; window: HexWindowData }
  | { type: "graph"; graph: CustodyGraphData }
  | { type: "diff"; diff: BundleDiffData }
  | { type: "failed"; message: string }
  | { type: "cleared-error" }
  | { type: "tab"; tab: LabTab }
  | { type: "string-query"; query: string }
  | { type: "string-kind"; kind: string }
  | { type: "offset-input"; value: string }
  | { type: "bytes-per-row"; value: number }
  | { type: "anchor"; offset: number | null }
  | { type: "head"; offset: number | null }
  | { type: "drag"; active: boolean }
  | { type: "queue"; items: IngestItem[] }
  | { type: "ingest-patch"; id: string; patch: Partial<IngestItem> }
  | { type: "notice"; tone: LabNotice["tone"]; message: string }
  | { type: "dismiss-notice"; id: number };

export function initialLabState(): LabState {
  return {
    manifest: null,
    report: null,
    window: null,
    graph: null,
    diff: null,
    ingest: [],
    tab: "hex",
    stringQuery: "",
    stringKind: "all",
    offsetInput: "0",
    bytesPerRow: 16,
    selectionAnchor: null,
    selectionHead: null,
    dragging: false,
    loading: false,
    error: "",
    notices: [],
    noticeSequence: 0,
  };
}

export function labReducer(state: LabState, action: LabAction): LabState {
  switch (action.type) {
    case "manifest":
      return { ...state, manifest: action.manifest };
    case "loading":
      return { ...state, loading: true, error: "" };
    case "report":
      return {
        ...state,
        loading: false,
        report: action.report,
        window: action.report.hex_window,
        tab: action.report.hex_window ? state.tab : "strings",
      };
    case "window":
      return { ...state, window: action.window };
    case "graph":
      return { ...state, graph: action.graph };
    case "diff":
      return { ...state, diff: action.diff };
    case "failed":
      return { ...state, loading: false, error: action.message };
    case "cleared-error":
      return { ...state, error: "" };
    case "tab":
      return { ...state, tab: action.tab };
    case "string-query":
      return { ...state, stringQuery: action.query };
    case "string-kind":
      return { ...state, stringKind: action.kind };
    case "offset-input":
      return { ...state, offsetInput: action.value };
    case "bytes-per-row":
      return { ...state, bytesPerRow: action.value };
    case "anchor":
      return {
        ...state,
        selectionAnchor: action.offset,
        selectionHead: action.offset === null ? null : state.selectionHead,
        window: state.window
          ? markSelection(
              state.window,
              selectionBounds(action.offset, state.selectionHead),
            )
          : null,
      };
    case "head":
      return {
        ...state,
        selectionHead: action.offset,
        window: state.window
          ? markSelection(
              state.window,
              selectionBounds(state.selectionAnchor, action.offset),
            )
          : null,
      };
    case "drag":
      return { ...state, dragging: action.active };
    case "queue":
      return { ...state, ingest: dedupeIngest(state.ingest, action.items) };
    case "ingest-patch":
      return {
        ...state,
        ingest: updateIngestItem(state.ingest, action.id, action.patch),
      };
    case "notice":
      return {
        ...state,
        noticeSequence: state.noticeSequence + 1,
        notices: [
          ...state.notices,
          {
            id: state.noticeSequence + 1,
            tone: action.tone,
            message: action.message,
          },
        ].slice(-6),
      };
    case "dismiss-notice":
      return {
        ...state,
        notices: state.notices.filter((item) => item.id !== action.id),
      };
  }
}

export function selectedReport(state: LabState): EvidenceReportData | null {
  return state.report;
}

export function hasSelection(state: LabState): boolean {
  return state.selectionAnchor !== null || state.selectionHead !== null;
}

export function activeIngest(state: LabState): IngestItem[] {
  return state.ingest.filter((item) => item.phase !== "rejected");
}

export function noticesByTone(
  state: LabState,
  tone: LabNotice["tone"],
): LabNotice[] {
  return state.notices.filter((notice) => notice.tone === tone);
}
