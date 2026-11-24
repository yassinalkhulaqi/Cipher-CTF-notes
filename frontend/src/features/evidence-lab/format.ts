/** Pure formatting and parsing helpers for the evidence lab. */

import type { IntegrityBadgeData } from "./types";

const BASE64_ALPHABET =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`;
}

export function formatOffset(value: number, width = 8): string {
  const safe = Math.max(0, Math.floor(value));
  return safe.toString(16).padStart(width, "0");
}

export function parseOffset(text: string): number | null {
  const trimmed = text.trim().replace(/^0x/i, "");
  if (!trimmed) return null;
  const radix =
    /^[0-9a-f]+$/i.test(trimmed) && /[a-f]/i.test(trimmed) ? 16 : 10;
  if (!new RegExp(`^[0-9a-f]+$`, "i").test(trimmed)) return null;
  const value = Number.parseInt(trimmed, radix);
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function maskHash(value: string, visible = 10): string {
  if (!value) return "-";
  if (value.length <= visible * 2 + 3) return value;
  return `${value.slice(0, visible)}...${value.slice(-visible)}`;
}

export function groupCells(cells: readonly string[], groupSize = 4): string {
  const parts: string[] = [];
  for (let index = 0; index < cells.length; index += groupSize) {
    parts.push(cells.slice(index, index + groupSize).join(" "));
  }
  return parts.join("  ");
}

export function formatEntropy(value: number): string {
  if (!Number.isFinite(value)) return "-";
  return `${value.toFixed(3)} bits/B`;
}

export function formatSignedBytes(bytes: number): string {
  const sign = bytes > 0 ? "+" : bytes < 0 ? "-" : "";
  return `${sign}${formatBytes(Math.abs(bytes))}`;
}

export function truncateMiddle(value: string, max = 48): string {
  if (value.length <= max) return value;
  const half = Math.floor((max - 3) / 2);
  return `${value.slice(0, half)}...${value.slice(-half)}`;
}

export function badgeTone(
  badge: Pick<IntegrityBadgeData, "state" | "ok"> | null,
): "good" | "warn" | "bad" | "neutral" {
  if (!badge) return "neutral";
  if (badge.state === "verified" && badge.ok) return "good";
  if (badge.state === "mismatch") return "bad";
  if (badge.state === "unverified") return "warn";
  return "neutral";
}

export function badgeLabel(
  badge: Pick<IntegrityBadgeData, "state"> | null,
): string {
  if (!badge) return "NO DATA";
  return badge.state.toUpperCase();
}

export function kindLabel(kind: string): string {
  return kind
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function deltaTone(kind: string): "good" | "warn" | "bad" | "neutral" {
  if (kind === "added") return "good";
  if (kind === "modified") return "warn";
  if (kind === "removed") return "bad";
  return "neutral";
}

export function bytesToBase64(bytes: Uint8Array): string {
  let output = "";
  for (let index = 0; index < bytes.length; index += 3) {
    const a = bytes[index];
    const b = index + 1 < bytes.length ? bytes[index + 1] : 0;
    const c = index + 2 < bytes.length ? bytes[index + 2] : 0;
    const triplet = (a << 16) | (b << 8) | c;
    output += BASE64_ALPHABET[(triplet >> 18) & 63];
    output += BASE64_ALPHABET[(triplet >> 12) & 63];
    output +=
      index + 1 < bytes.length ? BASE64_ALPHABET[(triplet >> 6) & 63] : "=";
    output += index + 2 < bytes.length ? BASE64_ALPHABET[triplet & 63] : "=";
  }
  return output;
}

export function textToBase64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return bytesToBase64(bytes);
}

export function hexToBytes(value: string): Uint8Array {
  const clean = value.replace(/[\s:]/g, "");
  const length = Math.floor(clean.length / 2);
  const result = new Uint8Array(length);
  for (let index = 0; index < length; index += 1) {
    const byte = Number.parseInt(clean.slice(index * 2, index * 2 + 2), 16);
    result[index] = Number.isNaN(byte) ? 0 : byte;
  }
  return result;
}

export function percent(value: number): string {
  return `${Math.round(clamp(value, 0, 1) * 100)}%`;
}
