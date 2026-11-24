/** Reducer and request builders for the activity feature. */

import type { ActivityRequestBody } from "./client";
import { chipsToQuery } from "./filters";
import type {
  DigestCollection,
  DigestPeriod,
  DensityMode,
  FilterChipData,
  RetrospectiveSummary,
  SinceLastVisit,
  StreamResult,
} from "./types";
import { EMPTY_STREAM } from "./types";

export type ActivityTab = "stream" | "digest" | "retrospective";

export interface ActivityState {
  stream: StreamResult;
  query: string;
  chips: FilterChipData[];
  density: DensityMode;
  period: DigestPeriod;
  digests: DigestCollection | null;
  retrospective: RetrospectiveSummary | null;
  since: SinceLastVisit | null;
  selectedSequence: number;
  tab: ActivityTab;
  loading: boolean;
  error: string;
  timezone: string;
  now: number;
}

export type ActivityAction =
  | { type: "loading"; value?: boolean }
  | { type: "stream"; value: StreamResult }
  | { type: "query"; value: string }
  | { type: "chips"; value: FilterChipData[] }
  | { type: "toggle-chip"; value: FilterChipData }
  | { type: "remove-chip"; value: string }
  | { type: "clear-chips" }
  | { type: "density"; value: DensityMode }
  | { type: "period"; value: DigestPeriod }
  | { type: "digests"; value: DigestCollection }
  | { type: "retrospective"; value: RetrospectiveSummary }
  | { type: "since"; value: SinceLastVisit }
  | { type: "select"; value: number }
  | { type: "tab"; value: ActivityTab }
  | { type: "error"; value: string }
  | { type: "now"; value: number }
  | { type: "reset" };

export function initialActivityState(
  options: { now?: number; timezone?: string } = {},
): ActivityState {
  return {
    stream: EMPTY_STREAM,
    query: "",
    chips: [],
    density: "comfortable",
    period: "daily",
    digests: null,
    retrospective: null,
    since: null,
    selectedSequence: 0,
    tab: "stream",
    loading: false,
    error: "",
    timezone: options.timezone ?? "UTC",
    now: options.now ?? 0,
  };
}

export function activityReducer(state: ActivityState, action: ActivityAction): ActivityState {
  switch (action.type) {
    case "loading":
      return { ...state, loading: action.value ?? true, error: "" };
    case "stream":
      return { ...state, stream: action.value, loading: false, error: "" };
    case "query":
      return { ...state, query: action.value };
    case "chips":
      return { ...state, chips: [...action.value] };
    case "toggle-chip": {
      const exists = state.chips.some((chip) => chip.token === action.value.token);
      return {
        ...state,
        chips: exists
          ? state.chips.filter((chip) => chip.token !== action.value.token)
          : [...state.chips, action.value],
      };
    }
    case "remove-chip":
      return { ...state, chips: state.chips.filter((chip) => chip.token !== action.value) };
    case "clear-chips":
      return { ...state, chips: [], query: "" };
    case "density":
      return { ...state, density: action.value };
    case "period":
      return { ...state, period: action.value };
    case "digests":
      return { ...state, digests: action.value, loading: false };
    case "retrospective":
      return { ...state, retrospective: action.value, loading: false };
    case "since":
      return { ...state, since: action.value };
    case "select":
      return { ...state, selectedSequence: action.value };
    case "tab":
      return { ...state, tab: action.value };
    case "error":
      return { ...state, error: action.value, loading: false };
    case "now":
      return { ...state, now: action.value };
    case "reset":
      return initialActivityState({ now: state.now, timezone: state.timezone });
    default:
      return state;
  }
}

export function effectiveQuery(state: ActivityState): string {
  return [state.query.trim(), chipsToQuery(state.chips)].filter(Boolean).join(" ");
}

export function streamRequest(state: ActivityState): ActivityRequestBody {
  return {
    query: effectiveQuery(state),
    density: state.density,
    timezone: state.timezone,
    offset: 0,
    size: 100,
  };
}

export function digestRequest(state: ActivityState): ActivityRequestBody {
  return { period: state.period, generated_at: state.now };
}

export function retrospectiveRequest(state: ActivityState): ActivityRequestBody {
  const end = state.now || 1;
  return {
    start: Math.max(0, end - 30 * 24 * 60 * 60),
    end,
    top_limit: 5,
  };
}

export function stateSignature(state: ActivityState): string {
  return JSON.stringify({
    query: effectiveQuery(state),
    density: state.density,
    period: state.period,
    tab: state.tab,
  });
}
