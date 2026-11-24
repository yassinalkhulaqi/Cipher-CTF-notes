/** V3 API client for the security namespace. */

import { V3Client, type V3ClientOptions } from "../../v3/apiClient";
import type {
  AuditExportResponse,
  AuditList,
  LockedResponse,
  PolicyPreview,
  PolicySnapshot,
  PostureReport,
  RecoveryResponse,
  RotationResponse,
  SetupResponse,
  UnlockResponse,
  VaultEvent,
  VaultStatus,
} from "./types";

export class VaultSecurityClient {
  private readonly client: V3Client;

  constructor(client: V3Client) {
    this.client = client;
  }

  status(): Promise<VaultStatus> {
    return this.client.data<VaultStatus>("security", "status");
  }

  posture(): Promise<PostureReport> {
    return this.client.data<PostureReport>("security", "posture");
  }

  setup(
    passphrase: string,
    content: Record<string, unknown> = {},
    recoveryCount = 6,
  ): Promise<SetupResponse> {
    return this.client.data<SetupResponse>("security", "setup", {
      passphrase,
      content,
      recovery_count: recoveryCount,
    });
  }

  unlock(passphrase: string): Promise<UnlockResponse> {
    return this.client.data<UnlockResponse>("security", "unlock", { passphrase });
  }

  lock(): Promise<LockedResponse> {
    return this.client.data<LockedResponse>("security", "lock");
  }

  rotate(newPassphrase: string): Promise<RotationResponse> {
    return this.client.data<RotationResponse>("security", "rotate", {
      new_passphrase: newPassphrase,
    });
  }

  issueRecoveryCodes(passphrase: string, count = 6): Promise<string[]> {
    return this.client
      .data<{ recovery_codes: string[] }>("security", "recovery_issue", {
        passphrase,
        count,
      })
      .then((result) => result.recovery_codes);
  }

  recover(code: string, newPassphrase: string): Promise<RecoveryResponse> {
    return this.client.data<RecoveryResponse>("security", "recover", {
      code,
      new_passphrase: newPassphrase,
    });
  }

  policyGet(): Promise<PolicySnapshot> {
    return this.client.data<PolicySnapshot>("security", "policy_get");
  }

  policyUpdate(
    rules: Record<string, unknown>[],
    grants: string[] = [],
    revocations: string[] = [],
  ): Promise<PolicySnapshot> {
    return this.client.data<PolicySnapshot>("security", "policy_update", {
      rules,
      grants,
      revocations,
    });
  }

  policyPreview(text: string, scope: string): Promise<PolicyPreview> {
    return this.client.data<PolicyPreview>("security", "policy_preview", {
      text,
      scope,
    });
  }

  auditList(filter: Record<string, unknown> = {}): Promise<AuditList> {
    return this.client.data<AuditList>("security", "audit_list", filter);
  }

  auditExport(format: "json" | "jsonl" = "json"): Promise<AuditExportResponse> {
    return this.client.data<AuditExportResponse>("security", "audit_export", {
      format,
    });
  }

  events(): Promise<VaultEvent[]> {
    return this.client
      .data<{ events: VaultEvent[] }>("security", "events")
      .then((result) => result.events);
  }
}

export function createVaultSecurityClient(
  options: V3ClientOptions = {},
): VaultSecurityClient {
  return new VaultSecurityClient(new V3Client(options));
}
