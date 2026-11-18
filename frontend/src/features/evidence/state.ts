import {
  DEFAULT_FILTERS,
  filterSummaries,
  maskHash,
  parseTags,
} from "./format";
import type {
  CustodyView,
  EvidenceDetail,
  EvidenceFilters,
  EvidenceKind,
  EvidenceManifest,
  EvidenceStats,
  EvidenceStatus,
  EvidenceSummary,
  IntegrityReport,
} from "./types";

export interface EvidenceNotice {
  id: number;
  tone: "info" | "good" | "warn" | "bad";
  message: string;
}

export interface EvidenceState {
  items: EvidenceSummary[];
  filters: EvidenceFilters;
  selectedId: string;
  detail: EvidenceDetail | null;
  custody: CustodyView | null;
  integrity: Record<string, IntegrityReport>;
  stats: EvidenceStats | null;
  manifest: EvidenceManifest | null;
  loading: boolean;
  error: string;
  notices: EvidenceNotice[];
  noticeSequence: number;
  dragging: boolean;
}

export type EvidenceAction =
  | { type: "loading" }
  | { type: "loaded"; items: EvidenceSummary[]; stats?: EvidenceStats | null }
  | { type: "failed"; message: string }
  | { type: "cleared-error" }
  | { type: "set-filter"; key: keyof EvidenceFilters; value: string }
  | { type: "reset-filters" }
  | { type: "select"; id: string }
  | { type: "detail"; detail: EvidenceDetail | null }
  | { type: "custody"; custody: CustodyView | null }
  | { type: "integrity"; id: string; report: IntegrityReport }
  | { type: "stats"; stats: EvidenceStats }
  | { type: "manifest"; manifest: EvidenceManifest | null }
  | { type: "upsert"; item: EvidenceSummary }
  | { type: "remove"; id: string }
  | { type: "notice"; tone: EvidenceNotice["tone"]; message: string }
  | { type: "dismiss-notice"; id: number }
  | { type: "drag"; active: boolean }
  | { type: "status"; id: string; status: EvidenceStatus };

export function initialEvidenceState(): EvidenceState {
  return {
    items: [],
    filters: { ...DEFAULT_FILTERS },
    selectedId: "",
    detail: null,
    custody: null,
    integrity: {},
    stats: null,
    manifest: null,
    loading: false,
    error: "",
    notices: [],
    noticeSequence: 0,
    dragging: false,
  };
}

function upsert(
  items: readonly EvidenceSummary[],
  item: EvidenceSummary,
): EvidenceSummary[] {
  const index = items.findIndex((candidate) => candidate.id === item.id);
  if (index < 0) return [...items, item];
  const next = [...items];
  next[index] = item;
  return next;
}

export function evidenceReducer(
  state: EvidenceState,
  action: EvidenceAction,
): EvidenceState {
  switch (action.type) {
    case "loading":
      return { ...state, loading: true, error: "" };
    case "loaded":
      return {
        ...state,
        items: action.items,
        stats: action.stats === undefined ? state.stats : action.stats,
        loading: false,
        error: "",
      };
    case "failed":
      return { ...state, loading: false, error: action.message };
    case "cleared-error":
      return { ...state, error: "" };
    case "set-filter":
      return {
        ...state,
        filters: {
          ...state.filters,
          [action.key]: action.value,
        } as EvidenceFilters,
      };
    case "reset-filters":
      return { ...state, filters: { ...DEFAULT_FILTERS } };
    case "select":
      return { ...state, selectedId: action.id, detail: null, custody: null };
    case "detail":
      return { ...state, detail: action.detail };
    case "custody":
      return { ...state, custody: action.custody };
    case "integrity":
      return {
        ...state,
        integrity: { ...state.integrity, [action.id]: action.report },
      };
    case "stats":
      return { ...state, stats: action.stats };
    case "manifest":
      return { ...state, manifest: action.manifest };
    case "upsert":
      return {
        ...state,
        items: upsert(state.items, action.item),
        selectedId: action.item.id,
      };
    case "remove":
      return {
        ...state,
        items: state.items.filter((item) => item.id !== action.id),
        selectedId: state.selectedId === action.id ? "" : state.selectedId,
        detail: state.detail?.record.id === action.id ? null : state.detail,
        custody: state.custody?.events.some(
          (event) => event.evidence_id === action.id,
        )
          ? null
          : state.custody,
      };
    case "notice": {
      const noticeSequence = state.noticeSequence + 1;
      return {
        ...state,
        noticeSequence,
        notices: [
          ...state.notices.slice(-4),
          { id: noticeSequence, tone: action.tone, message: action.message },
        ],
      };
    }
    case "dismiss-notice":
      return {
        ...state,
        notices: state.notices.filter((notice) => notice.id !== action.id),
      };
    case "drag":
      return { ...state, dragging: action.active };
    case "status":
      return {
        ...state,
        items: state.items.map((item) =>
          item.id === action.id ? { ...item, status: action.status } : item,
        ),
        detail:
          state.detail?.record.id === action.id
            ? {
                ...state.detail,
                record: { ...state.detail.record, status: action.status },
              }
            : state.detail,
      };
    default:
      return state;
  }
}

export function selectVisible(state: EvidenceState): EvidenceSummary[] {
  return filterSummaries(state.items, state.filters);
}

export function selectSelected(state: EvidenceState): EvidenceSummary | null {
  return state.items.find((item) => item.id === state.selectedId) ?? null;
}

export function selectIntegrity(
  state: EvidenceState,
  id = state.selectedId,
): IntegrityReport | undefined {
  return state.integrity[id];
}

export function selectTagOptions(state: EvidenceState): string[] {
  const options = new Set<string>();
  for (const item of state.items) for (const tag of item.tags) options.add(tag);
  if (state.filters.tag) options.add(state.filters.tag);
  return [...options].sort((a, b) => a.localeCompare(b));
}

export function describeSelection(state: EvidenceState): string {
  const selected = selectSelected(state);
  if (!selected) return "No evidence selected";
  return `${selected.id} · ${selected.title} · ${maskHash(selected.sha256)}`;
}

export function hasActiveFilters(filters: EvidenceFilters): boolean {
  return Boolean(
    filters.query ||
      filters.tag ||
      filters.hashPrefix ||
      filters.status ||
      filters.kind,
  );
}

export function filtersFromTags(tags: readonly string[]): EvidenceFilters {
  return { ...DEFAULT_FILTERS, tag: parseTags(tags.join(", "))[0] ?? "" };
}

export function statusOptions(
  statuses: readonly EvidenceStatus[],
): Array<{ value: string; label: string }> {
  return statuses.map((status) => ({
    value: status,
    label: status
      .replace(/_/g, " ")
      .replace(/^./, (char) => char.toUpperCase()),
  }));
}

export function kindOptions(
  kinds: readonly EvidenceKind[],
): Array<{ value: string; label: string }> {
  return kinds.map((kind) => ({
    value: kind,
    label: kind.replace(/_/g, " ").replace(/^./, (char) => char.toUpperCase()),
  }));
}

export function summaryFromRecord(record: {
  id: string;
  title: string;
  kind: EvidenceKind;
  status: EvidenceStatus;
  original_filename: string;
  mime: { mime_type: string };
  digests: { sha256: string; md5: string; size_bytes: number };
  tags: string[];
  note_id: number | null;
  thumbnail: { preview_kind: string; available: boolean };
  created_at: string;
  updated_at: string;
}): EvidenceSummary {
  return {
    id: record.id,
    title: record.title,
    kind: record.kind,
    status: record.status,
    original_filename: record.original_filename,
    mime_type: record.mime.mime_type,
    sha256: record.digests.sha256,
    md5: record.digests.md5,
    size_bytes: record.digests.size_bytes,
    tags: record.tags,
    note_id: record.note_id,
    preview_kind: record.thumbnail.preview_kind,
    has_thumbnail: record.thumbnail.available,
    created_at: record.created_at,
    updated_at: record.updated_at,
  };
}
