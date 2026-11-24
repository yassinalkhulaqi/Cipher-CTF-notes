/** Recovery flow with a deliberate confirmation step. */

import { useState } from "react";

import { V3Panel } from "../../v3/components/V3Panel";
import { checkPassphrase, maskRecoveryCode } from "./pure";

export interface RecoveryFlowProps {
  busy: boolean;
  onRecover: (code: string, newPassphrase: string) => void;
}

export function RecoveryFlow({ busy, onRecover }: RecoveryFlowProps) {
  const [code, setCode] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const check = checkPassphrase(passphrase, confirmation);
  const canSubmit = code.trim().length > 0 && check.valid && confirmed && !busy;

  return (
    <V3Panel
      title="Recover the vault"
      subtitle="A code works once. Recovery re-keys the vault and replaces all codes."
      kind="evidence"
    >
      <form
        className="vs-recovery__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSubmit) return;
          onRecover(code.trim(), passphrase);
          setCode("");
          setPassphrase("");
          setConfirmation("");
          setConfirmed(false);
        }}
      >
        <label className="vs-field">
          <span>Recovery code</span>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="XXXXX-XXXXX-XXXXX"
            autoComplete="off"
            disabled={busy}
          />
        </label>
        {code.length > 0 && (
          <p className="vs-field__hint">{maskRecoveryCode(code)}</p>
        )}
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
          <span>Confirm new passphrase</span>
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
        <label className="vs-checkbox">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>This code will be consumed and cannot be used again.</span>
        </label>
        <button type="submit" data-tone="bad" disabled={!canSubmit}>
          Recover and re-key
        </button>
      </form>
      <p className="vs-locked">
        Recovery never displays existing vault content.
      </p>
    </V3Panel>
  );
}
