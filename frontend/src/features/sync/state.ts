import type {
  ConflictRecord,
  ConflictSession,
  DryRunReport,
  OperationLogEntry,
  ProgressReport,
  SyncNotice,
  SyncSelection,
  WizardStep,
} from "./types";
import {
  advanceWizard,
  buildWizardSteps,
  createOperationLogId,
  defaultSelection,
  filterActionableChanges,
  unresolvedConflicts,
} from "./helpers";

export interface SyncFeatureState {
  selection: SyncSelection;
  wizard: WizardStep[];
  progress: ProgressReport[];
  dryRun: DryRunReport | null;
  conflicts: ConflictRecord[];
  session: ConflictSession | null;
  logs: OperationLogEntry[];
  notice: SyncNotice | null;
  busy: boolean;
}

export type SyncFeatureAction =
  | { type: "selection"; value: Partial<SyncSelection> }
  | { type: "reset"; kind?: string }
  | { type: "wizard"; index: number; status?: WizardStep["status"] }
  | { type: "progress"; value: ProgressReport[] }
  | { type: "progress-push"; value: ProgressReport }
  | { type: "dry-run"; value: DryRunReport | null }
  | { type: "conflicts"; value: ConflictRecord[] }
  | { type: "session"; value: ConflictSession | null }
  | { type: "notice"; value: SyncNotice | null }
  | { type: "busy"; value: boolean }
  | {
      type: "log";
      value: Omit<OperationLogEntry, "id" | "at"> & { at?: string };
    };

export function initialSyncState(kind = "import"): SyncFeatureState {
  return {
    selection: defaultSelection(),
    wizard: buildWizardSteps(kind),
    progress: [],
    dryRun: null,
    conflicts: [],
    session: null,
    logs: [],
    notice: null,
    busy: false,
  };
}

export function syncReducer(
  state: SyncFeatureState,
  action: SyncFeatureAction,
): SyncFeatureState {
  switch (action.type) {
    case "selection":
      return { ...state, selection: { ...state.selection, ...action.value } };
    case "reset":
      return initialSyncState(action.kind ?? "import");
    case "wizard":
      return {
        ...state,
        wizard: advanceWizard(state.wizard, action.index, action.status),
      };
    case "progress":
      return { ...state, progress: action.value };
    case "progress-push":
      return { ...state, progress: [...state.progress, action.value] };
    case "dry-run":
      return {
        ...state,
        dryRun: action.value,
        conflicts: Array.isArray(action.value?.conflicts)
          ? (action.value?.conflicts as ConflictRecord[])
          : state.conflicts,
      };
    case "conflicts":
      return { ...state, conflicts: action.value };
    case "session":
      return {
        ...state,
        session: action.value,
        conflicts: action.value?.conflicts ?? state.conflicts,
      };
    case "notice":
      return { ...state, notice: action.value };
    case "busy":
      return { ...state, busy: action.value };
    case "log":
      return {
        ...state,
        logs: [
          {
            id: createOperationLogId("log"),
            at: action.value.at ?? new Date().toISOString(),
            operation: action.value.operation,
            status: action.value.status,
            summary: action.value.summary,
          },
          ...state.logs,
        ].slice(0, 50),
      };
    default:
      return state;
  }
}

export function selectActionableChangeCount(state: SyncFeatureState): number {
  return filterActionableChanges(state.dryRun?.changes ?? []).length;
}

export function selectUnresolvedCount(state: SyncFeatureState): number {
  return unresolvedConflicts(state.conflicts).length;
}

export function selectIsReadyToRun(state: SyncFeatureState): boolean {
  if (state.busy) return false;
  if (!state.dryRun) return false;
  if (!state.dryRun.valid && unresolvedConflicts(state.conflicts).length > 0) {
    return false;
  }
  return true;
}

export function selectLatestProgress(
  state: SyncFeatureState,
): ProgressReport | null {
  return state.progress[state.progress.length - 1] ?? null;
}

export function selectWizardHeadline(state: SyncFeatureState): string {
  const active = state.wizard.find((step) => step.status === "active");
  return active ? active.title : "Complete";
}

export function noticeForError(message: string): SyncNotice {
  return { tone: "danger", title: "Sync failed", message };
}

export function noticeForSuccess(title: string, message: string): SyncNotice {
  return { tone: "success", title, message };
}

export function noticeForWarning(title: string, message: string): SyncNotice {
  return { tone: "warning", title, message };
}
