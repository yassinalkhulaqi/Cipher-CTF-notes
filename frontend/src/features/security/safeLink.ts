import type { CommandSafety, PrivacyMode, UrlSafety } from "./types";
import { severityRank } from "./helpers";

export interface SafeLinkDecision {
  allowed: boolean;
  reason: string;
  requiresConfirmation: boolean;
  safety?: UrlSafety | null;
}

export interface SafeCommandDecision {
  allowed: boolean;
  reason: string;
  requiresConfirmation: boolean;
  safety?: CommandSafety | null;
}

export const DEFAULT_ALLOWED_SCHEMES = ["https:", "http:", "mailto:"];

export function normalizeUrlInput(value: string): string {
  return value.trim();
}

export function parseUrl(value: string): URL | null {
  const normalized = normalizeUrlInput(value);
  if (!normalized) return null;
  try {
    return new URL(normalized);
  } catch {
    try {
      return new URL(`https://${normalized}`);
    } catch {
      return null;
    }
  }
}

export function sanitizeHref(
  value: string,
  allowedSchemes = DEFAULT_ALLOWED_SCHEMES,
): string | null {
  const parsed = parseUrl(value);
  if (!parsed) return null;
  if (!allowedSchemes.includes(parsed.protocol)) return null;
  return parsed.toString();
}

export function isExternalUrl(value: string, origin?: string): boolean {
  const parsed = parseUrl(value);
  if (!parsed) return false;
  if (parsed.protocol === "mailto:") return true;
  if (!origin) return true;
  try {
    return parsed.origin !== new URL(origin).origin;
  } catch {
    return true;
  }
}

export function safeLinkDecision(
  url: string,
  privacy: PrivacyMode | null | undefined,
  safety: UrlSafety | null | undefined,
  options: { origin?: string; requireSafeResult?: boolean } = {},
): SafeLinkDecision {
  const sanitized = sanitizeHref(url);
  if (!sanitized) {
    return {
      allowed: false,
      reason: "Invalid or unsupported URL.",
      requiresConfirmation: false,
      safety,
    };
  }
  if (
    privacy &&
    !privacy.allow_external_links &&
    isExternalUrl(sanitized, options.origin)
  ) {
    return {
      allowed: false,
      reason: "External links are blocked by the current privacy mode.",
      requiresConfirmation: false,
      safety,
    };
  }
  if (safety && !safety.safe) {
    return {
      allowed: false,
      reason: safety.reasons[0]
        ? `Blocked: ${safety.reasons[0].replace(/[_:]/g, " ")}`
        : "URL failed safety checks.",
      requiresConfirmation: false,
      safety,
    };
  }
  if (options.requireSafeResult && !safety) {
    return {
      allowed: false,
      reason: "URL safety analysis is required before opening this link.",
      requiresConfirmation: false,
      safety,
    };
  }
  if (safety && severityRank(safety.risk) >= severityRank("medium")) {
    return {
      allowed: true,
      reason: "URL passed checks but should be reviewed before opening.",
      requiresConfirmation: true,
      safety,
    };
  }
  return {
    allowed: true,
    reason: "URL is allowed.",
    requiresConfirmation: false,
    safety,
  };
}

export function safeCommandDecision(
  command: string,
  privacy: PrivacyMode | null | undefined,
  safety: CommandSafety | null | undefined,
): SafeCommandDecision {
  const normalized = command.trim();
  if (!normalized) {
    return {
      allowed: false,
      reason: "Command is empty.",
      requiresConfirmation: false,
      safety,
    };
  }
  if (privacy && !privacy.allow_command_copy) {
    return {
      allowed: false,
      reason: "Command copying is disabled by the current privacy mode.",
      requiresConfirmation: false,
      safety,
    };
  }
  if (safety && !safety.safe) {
    const destructive =
      safety.destructive ||
      safety.risk === "critical" ||
      safety.risk === "high";
    return {
      allowed: !destructive,
      reason: destructive
        ? "Command is blocked due to high-risk patterns."
        : "Command has safety warnings and requires confirmation.",
      requiresConfirmation: !destructive,
      safety,
    };
  }
  if (safety && (safety.networked || safety.privileged)) {
    return {
      allowed: true,
      reason: "Command may have side effects; review before use.",
      requiresConfirmation: true,
      safety,
    };
  }
  return {
    allowed: true,
    reason: "Command is allowed.",
    requiresConfirmation: false,
    safety,
  };
}

export function safeLinkAttributes(
  href: string,
  options: { external?: boolean; noreferrer?: boolean } = {},
): Record<string, string> {
  const attrs: Record<string, string> = { href };
  const external = options.external ?? isExternalUrl(href);
  if (external) {
    attrs.target = "_blank";
    const rel = ["noopener"];
    if (options.noreferrer !== false) rel.push("noreferrer");
    attrs.rel = rel.join(" ");
  }
  return attrs;
}

export function redactUrlForDisplay(url: string): string {
  const parsed = parseUrl(url);
  if (!parsed) return truncateMiddle(url, 64);
  if (parsed.username || parsed.password) {
    parsed.username = "***";
    parsed.password = "***";
  }
  const text = parsed.toString();
  return truncateMiddle(text, 80);
}

export function truncateMiddle(text: string, max = 80): string {
  if (text.length <= max) return text;
  if (max <= 10) return `${text.slice(0, max)}…`;
  const keep = max - 1;
  const start = Math.ceil(keep * 0.6);
  const end = keep - start;
  return `${text.slice(0, start)}…${text.slice(-end)}`;
}

export function formatCommandPreview(command: string, max = 120): string {
  const normalized = command.replace(/\s+/g, " ").trim();
  return normalized.length <= max
    ? normalized
    : `${normalized.slice(0, max - 1)}…`;
}
