import type { CaptureItemV4, CaptureSourceV4, TriageStateV4 } from "./client";
import { CAPTURE_SOURCES, TRIAGE_STATES } from "./client";

export type StateFilter = TriageStateV4 | "all";
export type SourceFilter = CaptureSourceV4 | "all";

export interface InboxState {
  items: CaptureItemV4[];
  draft: string;
  source: CaptureSourceV4;
  tags: string[];
  filter: StateFilter;
  sourceFilter: SourceFilter;
  query: string;
  selectedId: string;
  loading: boolean;
  submitting: boolean;
  error: string;
  notice: string;
  page: number;
  total: number;
  nextCursor: string;
  requestId: string;
}

export type InboxAction =
  | { type: "draft"; value: string }
  | { type: "source"; value: CaptureSourceV4 }
  | { type: "toggle-tag"; value: string }
  | { type: "filter"; value: StateFilter }
  | { type: "source-filter"; value: SourceFilter }
  | { type: "query"; value: string }
  | { type: "loading" }
  | {
      type: "loaded";
      items: CaptureItemV4[];
      total: number;
      page: number;
      nextCursor: string;
      requestId?: string;
    }
  | { type: "submitting" }
  | {
      type: "captured";
      item: CaptureItemV4;
      created: boolean;
      duplicate: boolean;
    }
  | { type: "triaged"; item: CaptureItemV4 }
  | { type: "failed"; message: string }
  | { type: "notice"; message: string }
  | { type: "select"; id: string }
  | { type: "move"; delta: number }
  | { type: "reset-composer" }
  | { type: "reset"; state: InboxState };

const LEGAL_TRANSITIONS: Readonly<
  Record<TriageStateV4, readonly TriageStateV4[]>
> = {
  untriaged: ["accepted", "rejected", "archived"],
  accepted: ["archived"],
  rejected: ["archived"],
  archived: ["untriaged"],
};

export function normalizeTag(tag: string): string {
  return tag
    .trim()
    .toLowerCase()
    .replace(/^#+\s*/, "")
    .replace(/\s+/g, "-");
}

export function initialInboxState(
  overrides: Partial<InboxState> = {},
): InboxState {
  return {
    items: [],
    draft: "",
    source: "manual",
    tags: [],
    filter: "all",
    sourceFilter: "all",
    query: "",
    selectedId: "",
    loading: false,
    submitting: false,
    error: "",
    notice: "",
    page: 1,
    total: 0,
    nextCursor: "",
    requestId: "",
    ...overrides,
  };
}

export function isLegalTransition(
  current: TriageStateV4,
  target: TriageStateV4,
): boolean {
  return LEGAL_TRANSITIONS[current].includes(target);
}

export function legalTargets(current: TriageStateV4): readonly TriageStateV4[] {
  return LEGAL_TRANSITIONS[current];
}

export function visibleItems(state: InboxState): CaptureItemV4[] {
  const needle = state.query.trim().toLowerCase();
  return state.items.filter((item) => {
    if (state.filter !== "all" && item.state !== state.filter) return false;
    if (state.sourceFilter !== "all" && item.source !== state.sourceFilter)
      return false;
    if (!needle) return true;
    return (
      item.raw.toLowerCase().includes(needle) ||
      item.tags.some((tag) => tag.toLowerCase().includes(needle))
    );
  });
}

export function selectedItem(state: InboxState): CaptureItemV4 | undefined {
  return state.items.find((item) => item.id === state.selectedId);
}

export function stateCounts(state: InboxState): Record<StateFilter, number> {
  const counts: Record<StateFilter, number> = {
    all: state.items.length,
    untriaged: 0,
    accepted: 0,
    rejected: 0,
    archived: 0,
  };
  for (const item of state.items) counts[item.state] += 1;
  return counts;
}

export function sourceCounts(state: InboxState): Record<SourceFilter, number> {
  const counts: Record<SourceFilter, number> = {
    all: state.items.length,
    manual: 0,
    link: 0,
    snippet: 0,
    flag: 0,
    clipboard: 0,
  };
  for (const item of state.items) counts[item.source] += 1;
  return counts;
}

export function capturePreview(raw: string, length = 96): string {
  const flat = raw.replace(/\s+/g, " ").trim();
  return flat.length > length ? `${flat.slice(0, length - 1)}…` : flat;
}

function replaceItem(
  items: CaptureItemV4[],
  item: CaptureItemV4,
): CaptureItemV4[] {
  const index = items.findIndex((candidate) => candidate.id === item.id);
  if (index < 0) return [item, ...items];
  const next = items.slice();
  next[index] = item;
  return next;
}

function moveSelection(state: InboxState, delta: number): InboxState {
  const items = visibleItems(state);
  if (items.length === 0) return state;
  const current = items.findIndex((item) => item.id === state.selectedId);
  const offset = delta > 0 ? 1 : -1;
  const nextIndex =
    current < 0
      ? offset > 0
        ? 0
        : items.length - 1
      : (current + offset + items.length) % items.length;
  return { ...state, selectedId: items[nextIndex].id };
}

export function reduceInbox(
  state: InboxState,
  action: InboxAction,
): InboxState {
  switch (action.type) {
    case "draft":
      return { ...state, draft: action.value, error: "" };
    case "source":
      return CAPTURE_SOURCES.includes(action.value)
        ? { ...state, source: action.value }
        : state;
    case "toggle-tag": {
      const tag = normalizeTag(action.value);
      if (!tag) return state;
      const tags = state.tags.includes(tag)
        ? state.tags.filter((item) => item !== tag)
        : [...state.tags, tag].sort();
      return { ...state, tags };
    }
    case "filter":
      return action.value === "all" ||
        TRIAGE_STATES.some((item) => item === action.value)
        ? { ...state, filter: action.value, selectedId: "" }
        : state;
    case "source-filter":
      return action.value === "all" ||
        CAPTURE_SOURCES.some((item) => item === action.value)
        ? { ...state, sourceFilter: action.value, selectedId: "" }
        : state;
    case "query":
      return { ...state, query: action.value, selectedId: "" };
    case "loading":
      return { ...state, loading: true, error: "" };
    case "loaded":
      return {
        ...state,
        items: action.items,
        total: action.total,
        page: action.page,
        nextCursor: action.nextCursor,
        requestId: action.requestId ?? state.requestId,
        loading: false,
        error: "",
      };
    case "submitting":
      return { ...state, submitting: true, error: "", notice: "" };
    case "captured":
      return {
        ...state,
        items: [
          action.item,
          ...state.items.filter((item) => item.id !== action.item.id),
        ],
        total: state.total + (action.created ? 1 : 0),
        selectedId: action.item.id,
        draft: "",
        tags: [],
        submitting: false,
        error: "",
        notice: action.duplicate
          ? "Duplicate already in inbox"
          : "Capture saved",
      };
    case "triaged":
      return {
        ...state,
        items: replaceItem(state.items, action.item),
        selectedId: action.item.id,
        submitting: false,
        error: "",
        notice: `Marked ${action.item.state}`,
      };
    case "failed":
      return {
        ...state,
        loading: false,
        submitting: false,
        error: action.message,
      };
    case "notice":
      return { ...state, notice: action.message, error: "" };
    case "select":
      return { ...state, selectedId: action.id };
    case "move":
      return moveSelection(state, action.delta);
    case "reset-composer":
      return { ...state, draft: "", tags: [], error: "", notice: "" };
    case "reset":
      return action.state;
    default:
      return state;
  }
}
