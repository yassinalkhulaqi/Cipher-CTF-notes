/** Reducer, selectors, and helpers for the security vault dashboard. */

import type {
  SealedEnvelopeView,
  VaultPrivacyMode,
  VaultRedactResult,
  VaultStatus,
} from "./types";

export type VaultTab = "posture" | "keys" | "recovery" | "privacy";
export type VaultNoticeTone = "info" | "good" | "warn" | "bad";

export interface VaultNotice {
  id: number;
  tone: VaultNoticeTone;
  message: string;
}

export interface VaultState {
  status: VaultStatus | null;
  envelope: SealedEnvelopeView | null;
  opened: string;
  recoveryCodes: string[];
  redaction: VaultRedactResult | null;
  activeTab: VaultTab;
  busy: boolean;
  error: string;
  notices: VaultNotice[];
  noticeSequence: number;
  lastAction: string;
}

export type VaultAction =
  | { type: "loaded"; status: VaultStatus }
  | { type: "loading"; action: string }
  | { type: "failed"; message: string }
  | { type: "cleared-error" }
  | { type: "sealed"; envelope: SealedEnvelopeView }
  | { type: "opened"; plaintext: string }
  | { type: "key-changed"; status: VaultStatus; notice: string }
  | { type: "privacy"; mode: VaultPrivacyMode }
  | { type: "recovery"; codes: string[]; remaining: number }
  | { type: "recovery-consumed"; remaining: number }
  | { type: "redacted"; result: VaultRedactResult }
  | { type: "tab"; tab: VaultTab }
  | { type: "notice"; tone: VaultNoticeTone; message: string }
  | { type: "dismiss-notice"; id: number }
  | { type: "clear-secrets" };

export const VAULT_TABS: readonly VaultTab[] = [
  "posture",
  "keys",
  "recovery",
  "privacy",
];

export function initialVaultState(
  status: VaultStatus | null = null,
): VaultState {
  return {
    status,
    envelope: null,
    opened: "",
    recoveryCodes: [],
    redaction: null,
    activeTab: "posture",
    busy: false,
    error: "",
    notices: [],
    noticeSequence: 0,
    lastAction: "",
  };
}

function appendNotice(
  state: VaultState,
  tone: VaultNoticeTone,
  message: string,
): Pick<VaultState, "notices" | "noticeSequence"> {
  const noticeSequence = state.noticeSequence + 1;
  return {
    noticeSequence,
    notices: [...state.notices, { id: noticeSequence, tone, message }].slice(
      -6,
    ),
  };
}

function patchStatus(
  status: VaultStatus | null,
  patch: Partial<VaultStatus>,
): VaultStatus | null {
  return status === null ? null : { ...status, ...patch };
}

export function vaultReducer(
  state: VaultState,
  action: VaultAction,
): VaultState {
  switch (action.type) {
    case "loaded":
      return {
        ...state,
        status: action.status,
        busy: false,
        error: "",
        lastAction: "status",
      };
    case "loading":
      return { ...state, busy: true, error: "", lastAction: action.action };
    case "failed":
      return {
        ...state,
        busy: false,
        error: action.message,
        ...appendNotice(state, "bad", action.message),
      };
    case "cleared-error":
      return { ...state, error: "" };
    case "sealed":
      return {
        ...state,
        busy: false,
        envelope: action.envelope,
        opened: "",
        status: patchStatus(state.status, {
          seal_count: (state.status?.seal_count ?? 0) + 1,
        }),
        ...appendNotice(state, "good", "Payload sealed and authenticated"),
      };
    case "opened":
      return {
        ...state,
        busy: false,
        opened: action.plaintext,
        status: patchStatus(state.status, {
          open_count: (state.status?.open_count ?? 0) + 1,
        }),
        ...appendNotice(state, "info", "Envelope opened and verified"),
      };
    case "key-changed":
      return {
        ...state,
        busy: false,
        status: action.status,
        envelope: null,
        opened: "",
        ...appendNotice(state, "good", action.notice),
      };
    case "privacy":
      return {
        ...state,
        busy: false,
        status: patchStatus(state.status, { privacy_mode: action.mode }),
        ...appendNotice(state, "info", `Privacy mode set to ${action.mode}`),
      };
    case "recovery":
      return {
        ...state,
        busy: false,
        recoveryCodes: action.codes,
        status: patchStatus(state.status, {
          recovery_remaining: action.remaining,
        }),
        ...appendNotice(state, "warn", "Store these one-time codes now"),
      };
    case "recovery-consumed":
      return {
        ...state,
        busy: false,
        status: patchStatus(state.status, {
          recovery_remaining: action.remaining,
        }),
        ...appendNotice(state, "good", "Recovery code consumed"),
      };
    case "redacted":
      return { ...state, busy: false, redaction: action.result };
    case "tab":
      return { ...state, activeTab: action.tab };
    case "notice":
      return { ...state, ...appendNotice(state, action.tone, action.message) };
    case "dismiss-notice":
      return {
        ...state,
        notices: state.notices.filter((item) => item.id !== action.id),
      };
    case "clear-secrets":
      return { ...state, envelope: null, opened: "", recoveryCodes: [] };
    default:
      return state;
  }
}

export function privacyLabel(mode: VaultPrivacyMode): string {
  if (mode === "locked") return "Content locked";
  if (mode === "redacted") return "Fields redacted";
  return "Normal view";
}

export function postureTone(level: string): VaultNoticeTone {
  if (level === "strong") return "good";
  if (level === "fair") return "warn";
  return "bad";
}

export function canSeal(state: VaultState): boolean {
  return state.status?.key_state === "active" && !state.busy;
}

export function versionLabel(state: VaultState): string {
  const version = state.status?.key_version ?? 0;
  const stateName = state.status?.key_state ?? "none";
  return version === 0 ? "No key" : `v${version} ${stateName}`;
}

export function noticeCounts(
  state: VaultState,
): Record<VaultNoticeTone, number> {
  const counts: Record<VaultNoticeTone, number> = {
    info: 0,
    good: 0,
    warn: 0,
    bad: 0,
  };
  for (const notice of state.notices) counts[notice.tone] += 1;
  return counts;
}

export function summarizeVault(state: VaultState): string {
  const status = state.status;
  if (status === null) return "Vault status unavailable";
  return [
    `seal=${status.seal_status}`,
    `key=${versionLabel(state)}`,
    `privacy=${status.privacy_mode}`,
    `recovery=${status.recovery_remaining}`,
  ].join(" | ");
}
