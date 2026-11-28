/** Typed API client for the v4 security vault. */

import { V4ApiError, V4Client } from "../v4-kernel/client";
import type {
  VaultConsumeResult,
  VaultKeyPairResult,
  VaultLockResult,
  VaultOpenResult,
  VaultPrivacyMode,
  VaultPrivacyResult,
  VaultRedactResult,
  VaultRedactionRule,
  VaultRecoveryResult,
  VaultSealResult,
  VaultStatus,
  VaultUnlockResult,
} from "./types";

export class VaultClientError extends Error {
  readonly code: string;
  readonly details: string[];

  constructor(code: string, message: string, details: string[] = []) {
    super(message);
    this.name = "VaultClientError";
    this.code = code;
    this.details = details;
  }
}

export function describeVaultError(error: unknown): string {
  if (error instanceof VaultClientError || error instanceof V4ApiError) {
    const detail = error.details[0];
    return detail ? `${error.message} (${detail})` : error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected vault error";
}

export class VaultClient {
  constructor(private readonly client: V4Client = new V4Client()) {}

  async status(): Promise<VaultStatus> {
    try {
      const result = await this.client.get<VaultStatus>("/vault");
      return result.data;
    } catch (error) {
      throw VaultClient.translate(error);
    }
  }

  async initialize(passphrase: string): Promise<{ id: string }> {
    const data = await this.send<{ key: { id: string } }>({
      action: "initialize",
      passphrase,
    });
    return { id: data.key.id };
  }

  async seal(plaintext: string, aad = ""): Promise<VaultSealResult> {
    return this.send<VaultSealResult>({ action: "seal", plaintext, aad });
  }

  async open(envelope: unknown, aad = ""): Promise<VaultOpenResult> {
    return this.send<VaultOpenResult>({ action: "open", envelope, aad });
  }

  async rotate(passphrase: string): Promise<VaultKeyPairResult> {
    return this.send<VaultKeyPairResult>({ action: "rotate", passphrase });
  }

  async lock(): Promise<VaultLockResult> {
    return this.send<VaultLockResult>({ action: "lock" });
  }

  async unlock(passphrase: string): Promise<VaultUnlockResult> {
    return this.send<VaultUnlockResult>({ action: "unlock", passphrase });
  }

  async setPrivacy(mode: VaultPrivacyMode): Promise<VaultPrivacyResult> {
    return this.send<VaultPrivacyResult>({ action: "privacy", mode });
  }

  async redact(
    data: Record<string, unknown>,
    rules: VaultRedactionRule[],
    mode: VaultPrivacyMode,
  ): Promise<VaultRedactResult> {
    return this.send<VaultRedactResult>({
      action: "redact",
      data,
      rules,
      mode,
    });
  }

  async generateRecovery(count: number): Promise<VaultRecoveryResult> {
    return this.send<VaultRecoveryResult>({
      action: "recovery_generate",
      count,
    });
  }

  async consumeRecovery(code: string): Promise<VaultConsumeResult> {
    return this.send<VaultConsumeResult>({ action: "recovery_consume", code });
  }

  private static translate(error: unknown): unknown {
    if (error instanceof V4ApiError) {
      return new VaultClientError(error.code, error.message, error.details);
    }
    return error;
  }

  private async send<T>(body: Record<string, unknown>): Promise<T> {
    try {
      return await this.client.post<T>("/vault", body);
    } catch (error) {
      throw VaultClient.translate(error);
    }
  }
}

export const vaultClient = new VaultClient();
