/** Local UI state for the vault security feature. */

import { create } from "zustand";

import { safeErrorText } from "./pure";
import type {
  AuditList,
  PolicySnapshot,
  PostureReport,
  VaultStatus,
} from "./types";

export interface VaultSecurityStore {
  status: VaultStatus | null;
  posture: PostureReport | null;
  policy: PolicySnapshot | null;
  audit: AuditList | null;
  recoveryCodes: string[];
  busy: boolean;
  error: string;
  hydrate: (status: VaultStatus, posture: PostureReport) => void;
  setPolicy: (policy: PolicySnapshot) => void;
  setAudit: (audit: AuditList) => void;
  setRecoveryCodes: (codes: string[]) => void;
  setBusy: (busy: boolean) => void;
  setError: (message: string) => void;
  clearError: () => void;
  reset: () => void;
}

export const useVaultSecurityStore = create<VaultSecurityStore>((set) => ({
  status: null,
  posture: null,
  policy: null,
  audit: null,
  recoveryCodes: [],
  busy: false,
  error: "",
  hydrate: (status, posture) => set({ status, posture, error: "" }),
  setPolicy: (policy) => set({ policy }),
  setAudit: (audit) => set({ audit }),
  setRecoveryCodes: (recoveryCodes) => set({ recoveryCodes: [...recoveryCodes] }),
  setBusy: (busy) => set({ busy }),
  setError: (message) => set({ error: safeErrorText(message), busy: false }),
  clearError: () => set({ error: "" }),
  reset: () =>
    set({
      status: null,
      posture: null,
      policy: null,
      audit: null,
      recoveryCodes: [],
      busy: false,
      error: "",
    }),
}));

export function vaultSecuritySnapshot(): Pick<
  VaultSecurityStore,
  "status" | "posture" | "busy" | "error"
> {
  const state = useVaultSecurityStore.getState();
  return {
    status: state.status,
    posture: state.posture,
    busy: state.busy,
    error: state.error,
  };
}
