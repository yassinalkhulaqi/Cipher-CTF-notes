/** Feature composition for the vault security lifecycle. */

import { useCallback, useEffect, useMemo, useState } from "react";

import { AuditViewer } from "./AuditViewer";
import { PolicyEditor } from "./PolicyEditor";
import { PostureDashboard } from "./PostureDashboard";
import { RecoveryFlow } from "./RecoveryFlow";
import { SetupWizard } from "./SetupWizard";
import { createVaultSecurityClient } from "./client";
import { canShowContent, lockedMessage, needsUnlock } from "./pure";
import { useVaultSecurityStore } from "./store";
import type { AuditFilterState, PolicyPreview, PolicyRule } from "./types";

export interface SecurityFeatureProps {
  basePath?: string;
}

export function SecurityFeature({ basePath }: SecurityFeatureProps) {
  const client = useMemo(
    () => createVaultSecurityClient(basePath ? { basePath } : {}),
    [basePath],
  );
  const status = useVaultSecurityStore((state) => state.status);
  const posture = useVaultSecurityStore((state) => state.posture);
  const policy = useVaultSecurityStore((state) => state.policy);
  const audit = useVaultSecurityStore((state) => state.audit);
  const codes = useVaultSecurityStore((state) => state.recoveryCodes);
  const busy = useVaultSecurityStore((state) => state.busy);
  const error = useVaultSecurityStore((state) => state.error);
  const hydrate = useVaultSecurityStore((state) => state.hydrate);
  const setPolicy = useVaultSecurityStore((state) => state.setPolicy);
  const setAudit = useVaultSecurityStore((state) => state.setAudit);
  const setRecoveryCodes = useVaultSecurityStore((state) => state.setRecoveryCodes);
  const setBusy = useVaultSecurityStore((state) => state.setBusy);
  const setError = useVaultSecurityStore((state) => state.setError);
  const clearError = useVaultSecurityStore((state) => state.clearError);
  const [preview, setPreview] = useState<PolicyPreview | null>(null);
  const [auditFilter, setAuditFilter] = useState<AuditFilterState>({
    action: "",
    outcome: "",
    actor: "",
    limit: 50,
  });

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [nextStatus, nextPosture, nextPolicy, nextAudit] = await Promise.all([
        client.status(),
        client.posture(),
        client.policyGet(),
        client.auditList(auditFilter as unknown as Record<string, unknown>),
      ]);
      hydrate(nextStatus, nextPosture);
      setPolicy(nextPolicy);
      setAudit(nextAudit);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, [client, auditFilter, hydrate, setPolicy, setAudit, setError, setBusy]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = useCallback(
    async (action: () => Promise<void>) => {
      setBusy(true);
      clearError();
      try {
        await action();
        await refresh();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        setBusy(false);
      }
    },
    [refresh, setBusy, setError, clearError],
  );

  if (!status || !posture) {
    return <section className="vs-feature vs-locked">Loading security state...</section>;
  }

  const shownEntries = audit?.entries ?? [];
  return (
    <section className="vs-feature">
      <header className="vs-feature__head">
        <div>
          <h1 className="vs-feature__title">Vault security</h1>
          <p className="vs-feature__subtitle">{lockedMessage(status.state)}</p>
        </div>
        <div className="vs-feature__actions">
          <button type="button" onClick={() => void refresh()} disabled={busy}>
            Refresh
          </button>
          {status.state === "unlocked" ? (
            <button
              type="button"
              onClick={() => void run(async () => {
                await client.lock();
              })}
              disabled={busy}
            >
              Lock vault
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void run(async () => {
                await client.lock();
              })}
              disabled={busy || status.state === "uninitialized"}
            >
              Lock vault
            </button>
          )}
        </div>
      </header>
      {error && (
        <p className="vs-error" role="alert">
          {error}
        </p>
      )}
      <div className="vs-feature__grid">
        <PostureDashboard report={posture} onRefresh={() => void refresh()} busy={busy} />
        <SetupWizard
          state={status.state}
          codes={codes}
          busy={busy}
          onSubmit={(passphrase, count) =>
            void run(async () => {
              const result = await client.setup(passphrase, {}, count);
              setRecoveryCodes(result.recovery_codes);
            })
          }
          onRotate={(passphrase) =>
            void run(async () => {
              const result = await client.rotate(passphrase);
              setRecoveryCodes(result.recovery_codes);
            })
          }
          onAcknowledgeCodes={() => setRecoveryCodes([])}
        />
        <RecoveryFlow
          busy={busy}
          onRecover={(code, passphrase) =>
            void run(async () => {
              const result = await client.recover(code, passphrase);
              setRecoveryCodes(result.recovery_codes);
            })
          }
        />
        <AuditViewer
          entries={shownEntries}
          busy={busy}
          onFilter={(filter) => setAuditFilter(filter)}
          onExport={(format) =>
            void run(async () => {
              await client.auditExport(format);
            })
          }
        />
        {policy && (
          <PolicyEditor
            snapshot={policy}
            preview={preview}
            busy={busy}
            onPreview={(text, scope) =>
              void run(async () => {
                setPreview(await client.policyPreview(text, scope));
              })
            }
            onSave={(rules: PolicyRule[]) =>
              void run(async () => {
                await client.policyUpdate(rules as unknown as Record<string, unknown>[]);
              })
            }
          />
        )}
      </div>
      {!canShowContent(status.state) && needsUnlock(status.state) && (
        <p className="vs-locked">Vault content is hidden while locked.</p>
      )}
    </section>
  );
}

export default SecurityFeature;
