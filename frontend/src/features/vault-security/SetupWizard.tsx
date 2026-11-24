/** Setup and rotation wizard that never echoes a passphrase. */

import { useState } from "react";

import { V3Panel } from "../../v3/components/V3Panel";
import {
  checkPassphrase,
  maskRecoveryCode,
  recoveryWarning,
  printableCodes,
  wizardSteps,
} from "./pure";
import type { VaultState } from "./types";

export interface SetupWizardProps {
  state: VaultState;
  codes: string[];
  busy: boolean;
  onSubmit: (passphrase: string, recoveryCount: number) => void;
  onRotate: (passphrase: string) => void;
  onAcknowledgeCodes: () => void;
}

export function SetupWizard({
  state,
  codes,
  busy,
  onSubmit,
  onRotate,
  onAcknowledgeCodes,
}: SetupWizardProps) {
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [recoveryCount, setRecoveryCount] = useState(6);
  const [acknowledged, setAcknowledged] = useState(false);
  const [showCodes, setShowCodes] = useState(false);
  const check = checkPassphrase(passphrase, confirmation);
  const steps = wizardSteps(state, codes);
  const isSetup = state === "uninitialized";

  const clearInputs = () => {
    setPassphrase("");
    setConfirmation("");
    setAcknowledged(false);
  };

  return (
    <V3Panel
      title={isSetup ? "Set up vault encryption" : "Rotate vault key"}
      subtitle="Keys are derived locally; nothing leaves this device."
      kind="evidence"
    >
      <ol className="vs-wizard__steps">
        {steps.map((step) => (
          <li data-complete={step.complete} key={step.id}>
            {step.label}
          </li>
        ))}
      </ol>
      <form
        className="vs-wizard__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!check.valid || !acknowledged || busy) return;
          if (isSetup) onSubmit(passphrase, recoveryCount);
          else onRotate(passphrase);
          clearInputs();
        }}
      >
        <label className="vs-field">
          <span>New passphrase</span>
          <input
            type="password"
            autoComplete="new-password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            disabled={busy}
          />
        </label>
        <label className="vs-field">
          <span>Confirm passphrase</span>
          <input
            type="password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            disabled={busy}
          />
        </label>
        <p className="vs-field__hint" data-valid={check.valid}>
          {check.reason}
        </p>
        {isSetup && (
          <label className="vs-field">
            <span>Recovery codes to issue</span>
            <select
              value={recoveryCount}
              onChange={(event) => setRecoveryCount(Number(event.target.value))}
              disabled={busy}
            >
              {[2, 4, 6, 8].map((count) => (
                <option value={count} key={count}>
                  {count} codes
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="vs-checkbox">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          <span>I understand the passphrase cannot be recovered without a code.</span>
        </label>
        <button type="submit" disabled={!check.valid || !acknowledged || busy}>
          {isSetup ? "Encrypt vault" : "Rotate key"}
        </button>
      </form>
      {codes.length > 0 && (
        <div className="vs-wizard__codes" data-visible={showCodes}>
          <p>{recoveryWarning(codes)}</p>
          <button type="button" onClick={() => setShowCodes(!showCodes)}>
            {showCodes ? "Hide codes" : "Reveal codes"}
          </button>
          {showCodes && (
            <ol className="vs-codes">
              {codes.map((code) => (
                <li key={code}>{code}</li>
              ))}
            </ol>
          )}
          {!showCodes && (
            <p className="vs-locked">{maskRecoveryCode(codes[0] ?? "")}</p>
          )}
          <div className="vs-wizard__code-actions">
            <button
              type="button"
              onClick={() => void navigator.clipboard?.writeText(printableCodes(codes))}
            >
              Copy codes
            </button>
            <button
              type="button"
              onClick={() => {
                onAcknowledgeCodes();
                setShowCodes(false);
              }}
            >
              I saved these codes
            </button>
          </div>
        </div>
      )}
    </V3Panel>
  );
}
