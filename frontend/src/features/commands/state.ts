/** Reducer for palette navigation, argument entry, and focus restore. */

import type {
  CommandGroupResult,
  CommandHit,
  CommandInvocation,
  CommandSpec,
} from "./types";

export interface PaletteState {
  open: boolean;
  query: string;
  groups: CommandGroupResult[];
  selected: number;
  collapsed: string[];
  pending: CommandSpec | null;
  draft: Record<string, string>;
  restoreFocus: string | null;
  submitted: CommandInvocation | null;
}

export type PaletteAction =
  | { type: "open"; restoreFocus: string; groups: CommandGroupResult[] }
  | { type: "close" }
  | { type: "query"; value: string; groups: CommandGroupResult[] }
  | { type: "move"; delta: number }
  | { type: "jump"; index: number }
  | { type: "toggle-group"; group: string }
  | { type: "edit-arguments"; command: CommandSpec }
  | { type: "set-argument"; name: string; value: string }
  | { type: "submit" }
  | { type: "cancel-arguments" }
  | { type: "restore" };

export function initialPaletteState(): PaletteState {
  return {
    open: false,
    query: "",
    groups: [],
    selected: 0,
    collapsed: [],
    pending: null,
    draft: {},
    restoreFocus: null,
    submitted: null,
  };
}

export function flattenGroups(groups: CommandGroupResult[]): CommandHit[] {
  return groups.flatMap((group) => group.hits);
}

export function clampSelection(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(index, length - 1));
}

export function paletteReducer(
  state: PaletteState,
  action: PaletteAction,
): PaletteState {
  switch (action.type) {
    case "open":
      return {
        ...initialPaletteState(),
        open: true,
        groups: action.groups,
        restoreFocus: action.restoreFocus,
      };
    case "close":
      return { ...state, open: false, pending: null, draft: {} };
    case "query":
      return {
        ...state,
        query: action.value,
        groups: action.groups,
        selected: 0,
        pending: null,
        draft: {},
      };
    case "move": {
      const total = flattenGroups(state.groups).length;
      return {
        ...state,
        selected: clampSelection(state.selected + action.delta, total),
      };
    }
    case "jump":
      return {
        ...state,
        selected: clampSelection(
          action.index,
          flattenGroups(state.groups).length,
        ),
      };
    case "toggle-group": {
      const present = state.collapsed.includes(action.group);
      return {
        ...state,
        collapsed: present
          ? state.collapsed.filter((group) => group !== action.group)
          : [...state.collapsed, action.group],
      };
    }
    case "edit-arguments": {
      const draft: Record<string, string> = {};
      for (const argument of action.command.arguments)
        draft[argument.name] = argument.default;
      return { ...state, pending: action.command, draft };
    }
    case "set-argument":
      return {
        ...state,
        draft: { ...state.draft, [action.name]: action.value },
      };
    case "submit": {
      if (!state.pending) return state;
      const invocation: CommandInvocation = {
        command_id: state.pending.id,
        arguments: { ...state.draft },
        source: "palette",
        context_ref: "",
      };
      return {
        ...state,
        open: false,
        pending: null,
        draft: {},
        submitted: invocation,
      };
    }
    case "cancel-arguments":
      return { ...state, pending: null, draft: {} };
    case "restore":
      return { ...state, open: false, restoreFocus: null };
  }
}

export function focusRestoreTarget(state: PaletteState): string | null {
  return state.restoreFocus;
}

export function isCommandBarShortcut(event: KeyboardEvent): boolean {
  return (
    Boolean(event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k"
  );
}
