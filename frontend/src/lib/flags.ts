import type { FlagPattern } from "./types";

export type FlagFormatTone = "known" | "custom" | "invalid" | "empty";

export interface FlagFormat {
  tone: FlagFormatTone;
  label: string;
  detail: string;
  platform?: string;
  category?: string;
}

const FLAG_SHAPE = /^([A-Za-z][A-Za-z0-9_-]{0,31})\{([^{}\s].*)\}$/;

export function flagFormat(
  value: string,
  patterns: FlagPattern[],
): FlagFormat {
  const trimmed = value.trim();
  if (!trimmed) {
    return {
      tone: "empty",
      label: "No flag captured",
      detail: "Add a flag in note properties or capture one in the note body.",
    };
  }

  const match = FLAG_SHAPE.exec(trimmed);
  if (!match) {
    return {
      tone: "invalid",
      label: "Needs review",
      detail: "This value does not follow the usual prefix{value} shape.",
    };
  }

  const prefix = (match[1] ?? "").toLowerCase();
  const pattern = patterns.find(
    (item) =>
      item.prefix.toLowerCase() === prefix ||
      item.pattern_key.toLowerCase() === prefix,
  );

  if (pattern) {
    return {
      tone: "known",
      label: "Known format",
      detail: `${pattern.platform} · ${pattern.category}`,
      platform: pattern.platform,
      category: pattern.category,
    };
  }

  return {
    tone: "custom",
    label: "Custom prefix",
    detail: `The “${match[1]}” prefix is not in the format registry.`,
  };
}
