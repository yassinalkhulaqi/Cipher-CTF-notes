/** Reducer, selectors, and display helpers for the v4 evidence lab UI. */

import type {
  CustodyEntryV4,
  EvidenceRecordV4,
  HexRowV4,
  InspectionResultV4,
  StringHitV4,
} from "./types";

export type LabPanelV4 = "hex" | "strings" | "custody";
export type HashBadgeV4 = "verified" | "mismatch" | "pending";

export interface EvidenceLabStateV4 {
  records: EvidenceRecordV4[];
  selectedId: string;
  query: string;
  inspection: InspectionResultV4 | null;
  custody: CustodyEntryV4[];
  chainValid: boolean;
  panel: LabPanelV4;
  showAscii: boolean;
  minStringLength: number;
  loading: boolean;
  error: string | null;
  etag: string;
  total: number;
  loadCount: number;
}

export type EvidenceLabActionV4 =
  | { type: "load-start" }
  | {
      type: "records-loaded";
      records: EvidenceRecordV4[];
      etag: string;
      total: number;
    }
  | { type: "select"; id: string }
  | { type: "inspection-loaded"; result: InspectionResultV4 }
  | { type: "custody-loaded"; entries: CustodyEntryV4[]; valid: boolean }
  | { type: "query"; value: string }
  | { type: "panel"; value: LabPanelV4 }
  | { type: "toggle-ascii" }
  | { type: "min-length"; value: number }
  | { type: "error"; message: string }
  | { type: "clear-error" }
  | { type: "reset" };

export function initialEvidenceLabState(): EvidenceLabStateV4 {
  return {
    records: [],
    selectedId: "",
    query: "",
    inspection: null,
    custody: [],
    chainValid: true,
    panel: "hex",
    showAscii: true,
    minStringLength: 4,
    loading: false,
    error: null,
    etag: "",
    total: 0,
    loadCount: 0,
  };
}

export function evidenceLabReducer(
  state: EvidenceLabStateV4,
  action: EvidenceLabActionV4,
): EvidenceLabStateV4 {
  switch (action.type) {
    case "load-start":
      return {
        ...state,
        loading: true,
        error: null,
        loadCount: state.loadCount + 1,
      };
    case "records-loaded": {
      const selectedId = state.selectedId || action.records[0]?.id || "";
      return {
        ...state,
        records: action.records,
        total: action.total,
        etag: action.etag,
        selectedId,
        loading: false,
      };
    }
    case "select":
      return {
        ...state,
        selectedId: action.id,
        inspection: null,
        custody: [],
        chainValid: true,
        error: null,
        panel: "hex",
      };
    case "inspection-loaded":
      return { ...state, inspection: action.result, loading: false };
    case "custody-loaded":
      return { ...state, custody: action.entries, chainValid: action.valid };
    case "query":
      return { ...state, query: action.value };
    case "panel":
      return { ...state, panel: action.value };
    case "toggle-ascii":
      return { ...state, showAscii: !state.showAscii };
    case "min-length":
      return {
        ...state,
        minStringLength: Math.max(1, Math.min(64, action.value)),
      };
    case "error":
      return { ...state, error: action.message, loading: false };
    case "clear-error":
      return { ...state, error: null };
    case "reset":
      return initialEvidenceLabState();
    default:
      return state;
  }
}

export function visibleRecords(state: EvidenceLabStateV4): EvidenceRecordV4[] {
  const needle = state.query.trim().toLowerCase();
  if (!needle) return state.records;
  return state.records.filter(
    (record) =>
      record.name.toLowerCase().includes(needle) ||
      record.sha256.toLowerCase().includes(needle) ||
      record.tags.some((tag) => tag.toLowerCase().includes(needle)),
  );
}

export function selectedRecord(
  state: EvidenceLabStateV4,
): EvidenceRecordV4 | null {
  return state.records.find((record) => record.id === state.selectedId) ?? null;
}

export function hexRows(state: EvidenceLabStateV4): HexRowV4[] {
  return state.inspection?.hex_rows ?? [];
}

export function visibleStrings(state: EvidenceLabStateV4): StringHitV4[] {
  const hits = state.inspection?.strings ?? [];
  return hits.filter((hit) => hit.value.length >= state.minStringLength);
}

export function hashBadge(state: EvidenceLabStateV4): HashBadgeV4 {
  const verifications = state.inspection?.verifications ?? [];
  if (verifications.length === 0) return "pending";
  return verifications.every((item) => item.matches) ? "verified" : "mismatch";
}

export function badgeLabel(badge: HashBadgeV4): string {
  if (badge === "verified") return "Hashes verified";
  if (badge === "mismatch") return "Hash mismatch";
  return "Not inspected";
}

export function custodyTimeline(state: EvidenceLabStateV4): CustodyEntryV4[] {
  return [...state.custody].sort((left, right) =>
    left.timestamp.localeCompare(right.timestamp),
  );
}

export function canInspect(state: EvidenceLabStateV4): boolean {
  return state.selectedId !== "" && !state.loading;
}

export function totalSize(state: EvidenceLabStateV4): number {
  return state.records.reduce((sum, record) => sum + record.size, 0);
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
}

export function formatOffset(offset: number): string {
  return offset.toString(16).padStart(8, "0");
}

export function shortHash(digest: string): string {
  return digest.slice(0, 12);
}

export function formatTimestamp(timestamp: string): string {
  return timestamp.replace("T", " ").replace(/\.\d{3}Z$/, "Z");
}

export function statusText(state: EvidenceLabStateV4): string {
  if (state.error) return state.error;
  if (state.loading) return "Loading evidence…";
  return `${state.records.length} of ${state.total} items`;
}
