import { useReducer, useState } from "react";

import { V3Panel } from "../../../v3/components/V3Panel";
import type { PortabilityClient } from "../client";
import { noticeForError, noticeForSuccess, toErrorMessage } from "../pure";
import { initialPortabilityState, portabilityReducer, selectUnresolved } from "../state";
import type { Resolution, VectorView } from "../types";
import { BundleWizard } from "./BundleWizard";
import { ConflictWorkbench } from "./ConflictWorkbench";
import { DryRunPreviewPanel } from "./DryRunPreviewPanel";
import { TransferProgress } from "./TransferProgress";
import { VerificationReceiptView } from "./VerificationReceiptView";
import "../portability.css";

interface Props {
  client: PortabilityClient;
  entities?: unknown[];
  links?: unknown[];
  base?: unknown[];
  local?: unknown[];
}

export function PortabilityFeature({
  client,
  entities = [],
  links = [],
  base = [],
  local = [],
}: Props) {
  const [state, dispatch] = useReducer(portabilityReducer, undefined, initialPortabilityState);
  const [bundleId, setBundleId] = useState("");
  const [previewId, setPreviewId] = useState("");
  const [strategy, setStrategy] = useState("manual");

  function guard(operation: () => Promise<void>): void {
    dispatch({ type: "busy", value: true });
    operation()
      .catch((error: unknown) => dispatch({ type: "notice", value: noticeForError(toErrorMessage(error)) }))
      .finally(() => dispatch({ type: "busy", value: false }));
  }

  function handlePlanPreview(): void {
    guard(async () => {
      const preview = await client.planBundle(entities, links);
      dispatch({ type: "step", index: 1 });
      dispatch({
        type: "notice",
        value: noticeForSuccess("Bundle scoped", String(preview.headline ?? "Preview ready")),
      });
    });
  }

  function handleCreate(): void {
    guard(async () => {
      const created = await client.createBundle(state.plan, entities, links);
      const id = String(created.bundle_id ?? "");
      setBundleId(id);
      const vector: VectorView = await client.compareVectors(
        (created.vector as Record<string, number>) ?? {},
        {},
      );
      dispatch({ type: "vector", value: vector });
      dispatch({ type: "step", index: 2 });
      dispatch({ type: "notice", value: noticeForSuccess("Bundle sealed", id) });
    });
  }

  function handleVerify(): void {
    guard(async () => {
      const result = await client.verifyBundle(bundleId, state.plan.passphrase);
      dispatch({ type: "receipt", value: result.receipt });
      dispatch({
        type: "notice",
        value: noticeForSuccess("Bundle verified", result.receipt.receiptId),
      });
    });
  }

  function handlePreview(): void {
    guard(async () => {
      const preview = await client.previewImport(
        bundleId,
        state.plan.passphrase,
        base,
        local,
        state.plan.scope,
      );
      setPreviewId(preview.preview_id);
      dispatch({ type: "dry-run", value: preview });
      dispatch({ type: "step", index: 3 });
    });
  }

  function handleApply(): void {
    guard(async () => {
      const decisions: Record<string, string> = {};
      for (const conflict of state.conflicts) {
        if (conflict.resolution !== "unresolved") decisions[conflict.ref] = conflict.resolution;
      }
      const result = await client.resolveConflicts(previewId, decisions, "local", state.plan.deviceId);
      dispatch({
        type: "notice",
        value: noticeForSuccess(
          "Merge applied",
          `Ledger intact: ${String(result.ledger_intact)}`,
        ),
      });
      dispatch({ type: "receipt", value: result.receipt });
      dispatch({ type: "step", index: 5 });
    });
  }

  function handleTransfer(): void {
    guard(async () => {
      const progress = await client.beginTransfer(bundleId, 64 * 1024);
      dispatch({ type: "progress", value: progress });
      dispatch({ type: "step", index: 4 });
    });
  }

  function handleCancel(): void {
    guard(async () => {
      if (!state.progress) return;
      dispatch({ type: "progress", value: await client.cancelTransfer(state.progress.transferId) });
    });
  }

  function handleResume(): void {
    guard(async () => {
      if (!state.progress) return;
      dispatch({ type: "progress", value: await client.resumeTransfer(state.progress.transferId) });
    });
  }

  return (
    <V3Panel
      title="Safe vault portability"
      subtitle="Move, verify, and merge vaults without losing a decision."
      actions={
        <span className="portability-badge" data-tone={selectUnresolved(state) ? "warn" : "good"}>
          {selectUnresolved(state)} unresolved
        </span>
      }
    >
      <div className="portability-feature">
        {state.notice && (
          <div className="portability-notice" data-tone={state.notice.tone} role="status">
            <strong>{state.notice.title}</strong>
            <span>{state.notice.message}</span>
          </div>
        )}
        <BundleWizard
          plan={state.plan}
          wizard={state.wizard}
          busy={state.busy}
          onChange={(value) => dispatch({ type: "plan", value })}
          onNext={handlePlanPreview}
        />
        <div className="portability-actions">
          <button type="button" className="portability-button" onClick={handleCreate} disabled={state.busy}>
            Seal encrypted bundle
          </button>
          <button type="button" className="portability-button" onClick={handleVerify} disabled={state.busy || !bundleId}>
            Verify receipt
          </button>
          <button type="button" className="portability-button" onClick={handlePreview} disabled={state.busy || !bundleId}>
            Run dry import
          </button>
          <button type="button" className="portability-button" onClick={handleTransfer} disabled={state.busy || !bundleId}>
            Start transfer
          </button>
        </div>
        <DryRunPreviewPanel
          report={state.dryRun}
          vector={state.vector}
          onConfirm={handleApply}
          onBack={() => dispatch({ type: "step", index: 1 })}
        />
        <ConflictWorkbench
          conflicts={state.conflicts}
          strategy={strategy}
          onStrategy={setStrategy}
          onResolve={(ref: string, resolution: Resolution) =>
            dispatch({ type: "resolve", ref, resolution })
          }
          onApply={handleApply}
        />
        <TransferProgress progress={state.progress} onCancel={handleCancel} onResume={handleResume} />
        <VerificationReceiptView receipt={state.receipt} onArchive={() => undefined} />
      </div>
    </V3Panel>
  );
}

export default PortabilityFeature;
