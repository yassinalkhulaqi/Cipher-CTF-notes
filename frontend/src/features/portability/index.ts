/** Public surface of the V3 vault portability feature. */

import { registerFeature } from "../../v3/registry";

export { BundleWizard } from "./components/BundleWizard";
export { ConflictWorkbench } from "./components/ConflictWorkbench";
export { DryRunPreviewPanel } from "./components/DryRunPreviewPanel";
export {
  PortabilityFeature,
  default,
} from "./components/PortabilityFeature";
export { TransferProgress } from "./components/TransferProgress";
export { VerificationReceiptView } from "./components/VerificationReceiptView";
export {
  PortabilityClient,
  bundleCreateRequest,
  compact,
  createPortabilityClient,
  previewRequest,
  resolveRequest,
  transferChunkRequest,
  transferStartRequest,
} from "./client";
export type { PortabilityRequestOptions } from "./client";
export {
  REASON_CODES,
  RESOLUTIONS,
  WIZARD_LABELS,
  actionTone,
  advanceWizard,
  applyResolution,
  buildWizardSteps,
  canCancel,
  canResume,
  changesByAction,
  clamp,
  conflictCounts,
  currentStep,
  defaultPlan,
  diffRows,
  failedChecks,
  filterConflicts,
  formatBytes,
  formatTimestamp,
  groupConflicts,
  overlappingFields,
  passphraseScore,
  progressLabel,
  progressPercent,
  receiptVerdict,
  reasonHelp,
  reasonLabel,
  reasonTone,
  renderValue,
  resolutionLabel,
  resolutionTone,
  shortDigest,
  stableSortConflicts,
  strengthLabel,
  strengthTone,
  suggestResolution,
  summarizeDryRun,
  toErrorMessage,
  truncate,
  unresolvedCount,
  validatePlan,
  vectorRelationLabel,
  vectorSummary,
  vectorTone,
  wizardPercent,
} from "./pure";
export {
  initialPortabilityState,
  portabilityReducer,
  selectNotice,
  selectProgress,
  selectReadyToRun,
  selectReceipt,
  selectStep,
  selectUnresolved,
} from "./state";
export type {
  BundlePlan,
  ChangeAction,
  ChangeView,
  CheckView,
  ConflictView,
  DiffRow,
  DryRunView,
  NoticeView,
  PortabilityAction,
  PortabilityState,
  ProgressView,
  ReasonCode,
  ReceiptView,
  Resolution,
  Tone,
  TransferPhase,
  VectorView,
  WizardStatus,
  WizardStep,
  WizardStepId,
} from "./types";

/** Register the feature in the additive V3 feature registry. */
export function registerPortabilityFeature(): void {
  registerFeature({
    id: "portability",
    label: "Vault Portability",
    route: "/portability",
    order: 90,
    capability: "portability",
    icon: "shuffle",
  });
}
