/** Relationship editing gestures and an optimistic undo/redo history. */

import { edgeKey } from "./geometry";
import type {
  EditRecord,
  GraphEdge,
  GraphPayload,
  RelationshipDraft,
} from "./types";
import { EMPTY_DRAFT, LINK_KINDS } from "./types";

export type GesturePhase = "idle" | "source" | "target" | "confirm";

export interface GestureState {
  phase: GesturePhase;
  draft: RelationshipDraft;
  message: string;
}

export function initialGesture(): GestureState {
  return {
    phase: "idle",
    draft: { ...EMPTY_DRAFT },
    message: "Select a source entity to start a relationship.",
  };
}

export function selectNode(state: GestureState, id: string): GestureState {
  if (state.phase === "idle" || state.phase === "confirm") {
    return {
      phase: "source",
      draft: { ...EMPTY_DRAFT, source: id },
      message: "Now select a target entity.",
    };
  }
  if (state.phase === "source") {
    if (id === state.draft.source) {
      return { ...state, message: "Source and target must differ." };
    }
    return {
      phase: "target",
      draft: { ...state.draft, target: id },
      message: "Choose a relationship kind, then commit.",
    };
  }
  return { ...state, draft: { ...state.draft, target: id }, phase: "target" };
}

export function setGestureKind(
  state: GestureState,
  kind: string,
): GestureState {
  if (!LINK_KINDS.includes(kind)) return state;
  return {
    ...state,
    draft: { ...state.draft, kind },
    phase: state.phase === "idle" ? "source" : state.phase,
  };
}

export function setGestureLabel(
  state: GestureState,
  label: string,
): GestureState {
  return { ...state, draft: { ...state.draft, label } };
}

export function setGestureWeight(
  state: GestureState,
  weight: number,
): GestureState {
  return {
    ...state,
    draft: { ...state.draft, weight: Math.min(1, Math.max(0, weight)) },
  };
}

export function cancelGesture(state: GestureState): GestureState {
  if (state.phase === "idle") return state;
  return initialGesture();
}

export function commitGesture(state: GestureState): GestureState {
  if (!canCommit(state)) return state;
  return {
    phase: "idle",
    draft: { ...EMPTY_DRAFT },
    message: `Connected ${state.draft.source} to ${state.draft.target}.`,
  };
}

export function canCommit(state: GestureState): boolean {
  const { source, target, kind, weight } = state.draft;
  return Boolean(
    source && target && source !== target && kind && weight >= 0 && weight <= 1,
  );
}

export function describeGesture(state: GestureState): string {
  const { source, target, kind, label } = state.draft;
  if (state.phase === "idle") return state.message;
  if (state.phase === "source") return `Source: ${source}. ${state.message}`;
  if (state.phase === "target") {
    return `Target: ${target} via ${state.draft.kind}. ${state.message}`;
  }
  return `${source} —${label || kind}→ ${target}`;
}

export function validateDraft(
  draft: RelationshipDraft,
  graph: GraphPayload,
): string[] {
  const problems: string[] = [];
  if (!draft.source || !graph.nodes.some((node) => node.id === draft.source)) {
    problems.push("Select a valid source entity.");
  }
  if (!draft.target || !graph.nodes.some((node) => node.id === draft.target)) {
    problems.push("Select a valid target entity.");
  }
  if (draft.source && draft.source === draft.target) {
    problems.push("Source and target must be different.");
  }
  if (!LINK_KINDS.includes(draft.kind))
    problems.push("Choose a known relationship kind.");
  if (draft.weight < 0 || draft.weight > 1)
    problems.push("Weight must be between 0 and 1.");
  if (graph.edges.some((edge) => edgeKey(edge) === draftToKey(draft))) {
    problems.push("This typed relationship already exists.");
  }
  return problems;
}

function draftToKey(draft: RelationshipDraft): string {
  return `${draft.source}→${draft.target}:${draft.kind}`;
}

export function draftToBody(draft: RelationshipDraft): Record<string, unknown> {
  return {
    source: draft.source,
    target: draft.target,
    kind: draft.kind,
    label: draft.label,
    weight: draft.weight,
  };
}

export interface HistoryState {
  undo: EditRecord[];
  redo: EditRecord[];
  sequence: number;
  capacity: number;
}

export function initialHistory(capacity = 100): HistoryState {
  return { undo: [], redo: [], sequence: 0, capacity };
}

export function pushEdit(
  history: HistoryState,
  record: Omit<EditRecord, "sequence">,
): HistoryState {
  const full: EditRecord = { ...record, sequence: history.sequence + 1 };
  const undo = [...history.undo, full].slice(-history.capacity);
  return { ...history, undo, redo: [], sequence: full.sequence };
}

export function undoEdit(history: HistoryState): {
  history: HistoryState;
  record: EditRecord | null;
} {
  if (history.undo.length === 0) return { history, record: null };
  const undo = history.undo.slice();
  const record = undo.pop() as EditRecord;
  return {
    history: { ...history, undo, redo: [...history.redo, record] },
    record,
  };
}

export function redoEdit(history: HistoryState): {
  history: HistoryState;
  record: EditRecord | null;
} {
  if (history.redo.length === 0) return { history, record: null };
  const redo = history.redo.slice();
  const record = redo.pop() as EditRecord;
  return {
    history: { ...history, redo, undo: [...history.undo, record] },
    record,
  };
}

export function historySummary(history: HistoryState): string {
  if (history.undo.length === 0) return "No relationship edits yet.";
  const last = history.undo[history.undo.length - 1];
  return `${history.undo.length} edit(s) · last: ${last.action} #${last.sequence}`;
}

export function applyLocalEdge(
  graph: GraphPayload,
  edge: GraphEdge,
): GraphPayload {
  if (graph.edges.some((item) => edgeKey(item) === edgeKey(edge))) return graph;
  return { ...graph, edges: [...graph.edges, edge] };
}

export function removeLocalEdge(
  graph: GraphPayload,
  edge: GraphEdge,
): GraphPayload {
  return {
    ...graph,
    edges: graph.edges.filter((item) => edgeKey(item) !== edgeKey(edge)),
  };
}

export function draftToEdge(draft: RelationshipDraft): GraphEdge {
  return {
    source: draft.source,
    target: draft.target,
    kind: draft.kind,
    label: draft.label,
    weight: draft.weight,
    metadata: {},
  };
}

export function invertEdge(edge: GraphEdge): GraphEdge {
  return { ...edge, source: edge.target, target: edge.source };
}

export function historyToPayload(
  history: HistoryState,
): Record<string, unknown> {
  return {
    size: history.undo.length,
    redo_size: history.redo.length,
    can_undo: history.undo.length > 0,
    can_redo: history.redo.length > 0,
    sequence: history.sequence,
  };
}
