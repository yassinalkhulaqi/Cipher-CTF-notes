/** Security posture dashboard with key rotation, recovery, and privacy controls. */

import { useEffect, useReducer, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { describeVaultError, vaultClient } from "./client";
import type { VaultClient } from "./client";
import {
  VAULT_TABS,
  canSeal,
  initialVaultState,
  noticeCounts,
  postureTone,
  privacyLabel,
  summarizeVault,
  vaultReducer,
  versionLabel,
} from "./state";
import type { VaultNotice, VaultTab } from "./state";
import { PRIVACY_MODES } from "./types";
import type { VaultPrivacyMode, VaultStatus } from "./types";
import "./security-vault.css";

export interface VaultPanelProps {
  client?: VaultClient;
  initialStatus?: VaultStatus;
  title?: string;
}

interface StatProps {
  label: string;
  value: string;
  tone?: "info" | "good" | "warn" | "bad";
}

function Stat({ label, value, tone = "info" }: StatProps) {
  return (
    <div className={`sv-stat sv-stat--${tone}`}>
      <span className="sv-stat__label">{label}</span>
      <strong className="sv-stat__value">{value}</strong>
    </div>
  );
}

interface NoticeListProps {
  notices: VaultNotice[];
  onDismiss: (id: number) => void;
}

function NoticeList({ notices, onDismiss }: NoticeListProps) {
  if (notices.length === 0) return null;
  return (
    <ul className="sv-notices" aria-live="polite">
      {notices.map((notice) => (
        <li key={notice.id} className={`sv-notice sv-notice--${notice.tone}`}>
          <span>{notice.message}</span>
          <button
            type="button"
            className="sv-notice__close"
            aria-label={`Dismiss notice ${notice.id}`}
            onClick={() => onDismiss(notice.id)}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

interface TabButtonProps {
  tab: VaultTab;
  active: boolean;
  onSelect: (tab: VaultTab) => void;
}

function TabButton({ tab, active, onSelect }: TabButtonProps) {
  return (
    <button
      type="button"
      className={`sv-tab${active ? " sv-tab--active" : ""}`}
      aria-pressed={active}
      onClick={() => onSelect(tab)}
    >
      {tab}
    </button>
  );
}

function shortHex(value: string): string {
  return value.length > 12 ? `${value.slice(0, 12)}…` : value || "—";
}

export function VaultPanel({
  client,
  initialStatus,
  title = "Security vault",
}: VaultPanelProps) {
  const activeClient = client ?? vaultClient;
  const [state, dispatch] = useReducer(
    vaultReducer,
    initialStatus,
    initialVaultState,
  );
  const [plaintext, setPlaintext] = useState("");
  const [sealAad, setSealAad] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [unlockPassphrase, setUnlockPassphrase] = useState("");
  const [recoveryCount, setRecoveryCount] = useState(4);
  const [recoveryCode, setRecoveryCode] = useState("");
  const [redactionData, setRedactionData] = useState(
    '{"user":{"token":"abc"},"title":"report"}',
  );
  const [redactionRules, setRedactionRules] = useState(
    '[{"field":"user.token","replacement":"[hidden]"}]',
  );

  useEffect(() => {
    if (initialStatus !== undefined) return;
    let active = true;
    activeClient
      .status()
      .then((status) => {
        if (active) dispatch({ type: "loaded", status });
      })
      .catch((error: unknown) => {
        if (active)
          dispatch({ type: "failed", message: describeVaultError(error) });
      });
    return () => {
      active = false;
    };
  }, [activeClient, initialStatus]);

  const run = async (action: string, task: () => Promise<void>) => {
    dispatch({ type: "loading", action });
    try {
      await task();
    } catch (error: unknown) {
      dispatch({ type: "failed", message: describeVaultError(error) });
    }
  };

  const onSeal = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void run("seal", async () => {
      const result = await activeClient.seal(plaintext, sealAad);
      dispatch({ type: "sealed", envelope: result.envelope });
      setPlaintext("");
    });
  };

  const onOpen = () => {
    if (state.envelope === null) {
      dispatch({
        type: "notice",
        tone: "warn",
        message: "Seal a payload first",
      });
      return;
    }
    void run("open", async () => {
      const result = await activeClient.open(state.envelope, sealAad);
      dispatch({ type: "opened", plaintext: result.plaintext });
    });
  };

  const onInitialize = () => {
    void run("initialize", async () => {
      await activeClient.initialize(passphrase);
      await refresh();
      dispatch({ type: "notice", tone: "good", message: "Vault initialized" });
      setPassphrase("");
    });
  };

  const refresh = async () => {
    const status = await activeClient.status();
    dispatch({ type: "loaded", status });
  };

  const onRotate = () => {
    void run("rotate", async () => {
      await activeClient.rotate(passphrase);
      await refresh();
      dispatch({
        type: "notice",
        tone: "good",
        message: "Key rotated; old key retired",
      });
      setPassphrase("");
    });
  };

  const onLock = () => {
    void run("lock", async () => {
      await activeClient.lock();
      await refresh();
      dispatch({
        type: "notice",
        tone: "warn",
        message: "Key material cleared from memory",
      });
    });
  };

  const onUnlock = () => {
    void run("unlock", async () => {
      await activeClient.unlock(unlockPassphrase);
      await refresh();
      dispatch({ type: "notice", tone: "good", message: "Vault unlocked" });
      setUnlockPassphrase("");
    });
  };

  const onPrivacy = (mode: VaultPrivacyMode) => {
    void run("privacy", async () => {
      await activeClient.setPrivacy(mode);
      await refresh();
      dispatch({ type: "privacy", mode });
    });
  };

  const onGenerateRecovery = () => {
    void run("recovery_generate", async () => {
      const result = await activeClient.generateRecovery(recoveryCount);
      dispatch({
        type: "recovery",
        codes: result.codes,
        remaining: result.records.filter((record) => !record.used).length,
      });
    });
  };

  const onConsumeRecovery = () => {
    void run("recovery_consume", async () => {
      const result = await activeClient.consumeRecovery(recoveryCode);
      dispatch({ type: "recovery-consumed", remaining: result.remaining });
      setRecoveryCode("");
    });
  };

  const onRedact = () => {
    void run("redact", async () => {
      let data: Record<string, unknown>;
      let rules: { field: string; replacement: string }[];
      try {
        data = JSON.parse(redactionData) as Record<string, unknown>;
        rules = JSON.parse(redactionRules) as {
          field: string;
          replacement: string;
        }[];
      } catch {
        dispatch({
          type: "notice",
          tone: "bad",
          message: "Invalid JSON in redaction input",
        });
        return;
      }
      const result = await activeClient.redact(
        data,
        rules,
        state.status?.privacy_mode ?? "redacted",
      );
      dispatch({ type: "redacted", result });
    });
  };

  const status = state.status;
  const counts = noticeCounts(state);
  const tabContent: Record<VaultTab, ReactNode> = {
    posture: (
      <div className="sv-posture" data-testid="vault-posture">
        <div
          className="sv-score"
          aria-label={`Posture score ${status?.posture.score ?? 0}`}
        >
          <div className="sv-score__bar">
            <div
              className={`sv-score__fill sv-score__fill--${postureTone(status?.posture.level ?? "weak")}`}
              style={{ width: `${status?.posture.score ?? 0}%` }}
            />
          </div>
          <span className="sv-score__value">
            {status?.posture.score ?? 0} / 100
          </span>
        </div>
        <ul className="sv-checks">
          {(status?.posture.checks ?? []).map((check) => (
            <li key={check} className="sv-check">
              <span className="sv-check__dot" aria-hidden="true" />
              {check.replaceAll("-", " ")}
            </li>
          ))}
        </ul>
        <p className="sv-algorithm">
          {status?.algorithm ?? "No encryption algorithm reported"}
        </p>
      </div>
    ),
    keys: (
      <div className="sv-keys" data-testid="vault-keys">
        <form className="sv-form" onSubmit={onSeal}>
          <h3>Seal a payload</h3>
          <label htmlFor="sv-plaintext">Plaintext</label>
          <textarea
            id="sv-plaintext"
            value={plaintext}
            onChange={(event) => setPlaintext(event.target.value)}
            rows={3}
          />
          <label htmlFor="sv-seal-aad">Context label (authenticated)</label>
          <input
            id="sv-seal-aad"
            value={sealAad}
            onChange={(event) => setSealAad(event.target.value)}
            placeholder="finding:42"
          />
          <button
            type="submit"
            className="sv-btn sv-btn--primary"
            disabled={!canSeal(state)}
          >
            Seal
          </button>
        </form>
        <div className="sv-envelope">
          <h3>Sealed envelope</h3>
          {state.envelope === null ? (
            <p className="sv-empty">Nothing sealed yet.</p>
          ) : (
            <dl>
              <dt>Key ID</dt>
              <dd>{shortHex(state.envelope.key_id)}</dd>
              <dt>Nonce</dt>
              <dd className="sv-mono">{shortHex(state.envelope.nonce)}</dd>
              <dt>Ciphertext</dt>
              <dd className="sv-mono">
                {shortHex(state.envelope.ciphertext_hex)}
              </dd>
              <dt>MAC</dt>
              <dd className="sv-mono">{shortHex(state.envelope.mac_hex)}</dd>
            </dl>
          )}
          <button
            type="button"
            className="sv-btn"
            onClick={onOpen}
            disabled={state.busy}
          >
            Open &amp; verify
          </button>
          {state.opened !== "" && (
            <p className="sv-opened" data-testid="vault-opened">
              {state.opened}
            </p>
          )}
        </div>
        <div className="sv-rotate">
          <h3>Key lifecycle</h3>
          <label htmlFor="sv-passphrase">Passphrase</label>
          <input
            id="sv-passphrase"
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
          />
          <div className="sv-btn-row">
            <button
              type="button"
              className="sv-btn"
              onClick={onInitialize}
              disabled={state.busy}
            >
              Initialize
            </button>
            <button
              type="button"
              className="sv-btn sv-btn--primary"
              onClick={onRotate}
              disabled={state.busy}
            >
              Rotate
            </button>
            <button
              type="button"
              className="sv-btn"
              onClick={onLock}
              disabled={state.busy}
            >
              Lock
            </button>
          </div>
          <label htmlFor="sv-unlock">Unlock passphrase</label>
          <input
            id="sv-unlock"
            type="password"
            value={unlockPassphrase}
            onChange={(event) => setUnlockPassphrase(event.target.value)}
          />
          <button
            type="button"
            className="sv-btn"
            onClick={onUnlock}
            disabled={state.busy}
          >
            Unlock
          </button>
        </div>
      </div>
    ),
    recovery: (
      <div className="sv-recovery" data-testid="vault-recovery">
        <h3>Recovery codes</h3>
        <p className="sv-warning">
          Codes are shown once. Digests only are stored; save them offline now.
        </p>
        <label htmlFor="sv-count">Number of codes</label>
        <select
          id="sv-count"
          value={recoveryCount}
          onChange={(event) => setRecoveryCount(Number(event.target.value))}
        >
          {[2, 4, 6, 8].map((count) => (
            <option key={count} value={count}>
              {count}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="sv-btn"
          onClick={onGenerateRecovery}
          disabled={state.busy}
        >
          Generate
        </button>
        {state.recoveryCodes.length > 0 && (
          <ul className="sv-codes">
            {state.recoveryCodes.map((code) => (
              <li key={code} className="sv-mono">
                {code}
              </li>
            ))}
          </ul>
        )}
        <label htmlFor="sv-code">Consume a code</label>
        <input
          id="sv-code"
          value={recoveryCode}
          onChange={(event) => setRecoveryCode(event.target.value)}
        />
        <button
          type="button"
          className="sv-btn"
          onClick={onConsumeRecovery}
          disabled={state.busy}
        >
          Consume
        </button>
      </div>
    ),
    privacy: (
      <div className="sv-privacy" data-testid="vault-privacy">
        <h3>Privacy mode</h3>
        <div className="sv-mode-switch" role="group" aria-label="Privacy mode">
          {PRIVACY_MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              className={`sv-btn${status?.privacy_mode === mode ? " sv-btn--primary" : ""}`}
              aria-pressed={status?.privacy_mode === mode}
              onClick={() => onPrivacy(mode)}
              disabled={state.busy}
            >
              {mode}
            </button>
          ))}
        </div>
        <p className="sv-hint">
          {privacyLabel(status?.privacy_mode ?? "normal")}
        </p>
        <h3>Redaction preview</h3>
        <label htmlFor="sv-redact-data">Data (JSON)</label>
        <textarea
          id="sv-redact-data"
          value={redactionData}
          onChange={(event) => setRedactionData(event.target.value)}
          rows={4}
          className="sv-mono"
        />
        <label htmlFor="sv-redact-rules">Rules (JSON)</label>
        <textarea
          id="sv-redact-rules"
          value={redactionRules}
          onChange={(event) => setRedactionRules(event.target.value)}
          rows={3}
          className="sv-mono"
        />
        <button
          type="button"
          className="sv-btn sv-btn--primary"
          onClick={onRedact}
          disabled={state.busy}
        >
          Preview redaction
        </button>
        {state.redaction !== null && (
          <div className="sv-preview" data-testid="vault-redaction">
            <pre>{JSON.stringify(state.redaction.data, null, 2)}</pre>
            <p>Changed paths: {state.redaction.paths.join(", ") || "none"}</p>
          </div>
        )}
      </div>
    ),
  };

  return (
    <section className="sv-root" aria-label={title}>
      <header className="sv-header">
        <div>
          <h2 className="sv-title">{title}</h2>
          <p className="sv-subtitle" data-testid="vault-summary">
            {summarizeVault(state)}
          </p>
        </div>
        <div className="sv-badges">
          <span
            className={`sv-badge sv-badge--${postureTone(status?.posture.level ?? "weak")}`}
          >
            {status?.posture.level ?? "unknown"}
          </span>
          <span className="sv-badge">{versionLabel(state)}</span>
          {state.busy && (
            <span className="sv-badge sv-badge--busy">working…</span>
          )}
        </div>
      </header>
      <div className="sv-stats">
        <Stat label="Seal status" value={status?.seal_status ?? "loading"} />
        <Stat
          label="Key version"
          value={versionLabel(state)}
          tone={status?.key_state === "active" ? "good" : "warn"}
        />
        <Stat label="Seals" value={String(status?.seal_count ?? 0)} />
        <Stat label="Opens" value={String(status?.open_count ?? 0)} />
        <Stat
          label="Recovery codes"
          value={String(status?.recovery_remaining ?? 0)}
          tone={counts.warn > 0 ? "warn" : "info"}
        />
      </div>
      <nav className="sv-tabs" aria-label="Vault sections">
        {VAULT_TABS.map((tab) => (
          <TabButton
            key={tab}
            tab={tab}
            active={state.activeTab === tab}
            onSelect={(next) => dispatch({ type: "tab", tab: next })}
          />
        ))}
      </nav>
      {state.error !== "" && (
        <div className="sv-error" role="alert">
          {state.error}
          <button
            type="button"
            onClick={() => dispatch({ type: "cleared-error" })}
          >
            Dismiss
          </button>
        </div>
      )}
      <NoticeList
        notices={state.notices}
        onDismiss={(id) => dispatch({ type: "dismiss-notice", id })}
      />
      <div className="sv-panel v4-panel">{tabContent[state.activeTab]}</div>
      <footer className="sv-footer">
        <button
          type="button"
          className="sv-btn"
          onClick={() => void run("refresh", refresh)}
        >
          Refresh posture
        </button>
        <button
          type="button"
          className="sv-btn"
          onClick={() => dispatch({ type: "clear-secrets" })}
        >
          Clear local secrets
        </button>
      </footer>
    </section>
  );
}

export default VaultPanel;
