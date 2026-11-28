/** Wire types for the v4 security vault UI. */

export type VaultKeyState = "active" | "rotated" | "revoked" | "none";
export type VaultPrivacyMode = "normal" | "redacted" | "locked";
export type VaultPostureLevel = "strong" | "fair" | "weak";

export interface KeyMeta {
  id: string;
  version: number;
  state: VaultKeyState;
  created_at: string;
  rotated_at: string;
}

export interface SealedEnvelopeView {
  version: number;
  key_id: string;
  nonce: string;
  ciphertext_hex: string;
  mac_hex: string;
  aad: string;
}

export interface VaultPosture {
  level: VaultPostureLevel;
  score: number;
  checks: string[];
}

export interface VaultStatus {
  algorithm: string;
  envelope_version: number;
  key_id: string;
  key_state: VaultKeyState;
  key_version: number;
  fingerprint: string;
  open_count: number;
  posture: VaultPosture;
  privacy_mode: VaultPrivacyMode;
  recovery_remaining: number;
  seal_count: number;
  seal_status: string;
}

export interface VaultSealResult {
  envelope: SealedEnvelopeView;
  size: number;
}

export interface VaultOpenResult {
  aad: string;
  key_id: string;
  plaintext: string;
}

export interface VaultRedactionRule {
  field: string;
  replacement: string;
}

export interface VaultRedactResult {
  data: Record<string, unknown>;
  paths: string[];
  mode: VaultPrivacyMode;
}

export interface VaultKeyPairResult {
  previous: KeyMeta;
  current: KeyMeta;
}

export interface VaultRecoveryRecord {
  id: string;
  code_hash: string;
  used: boolean;
  created_at: string;
}

export interface VaultRecoveryResult {
  codes: string[];
  records: VaultRecoveryRecord[];
}

export interface VaultLockResult {
  forgotten: number;
  state: string;
}

export interface VaultUnlockResult {
  key_id: string;
  state: string;
  version: number;
}

export interface VaultPrivacyResult {
  privacy_mode: VaultPrivacyMode;
}

export interface VaultConsumeResult {
  id: string;
  remaining: number;
  used: boolean;
}

export const PRIVACY_MODES: readonly VaultPrivacyMode[] = [
  "normal",
  "redacted",
  "locked",
];
