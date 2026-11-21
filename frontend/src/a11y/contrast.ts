/** Minimal WCAG 2.2 contrast helpers used by the accessibility audit flow. */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

const clampChannel = (value: number): number =>
  Math.max(0, Math.min(255, Math.round(value)));

export function hexToRgb(hex: string): Rgb {
  const normalized = hex.replace(/^#/, "");
  const full =
    normalized.length === 3
      ? normalized
          .split("")
          .map((char) => char + char)
          .join("")
      : normalized;
  const value = Number.parseInt(full, 16);
  return {
    r: (value >> 16) & 0xff,
    g: (value >> 8) & 0xff,
    b: value & 0xff,
  };
}

export function rgbToHex({ r, g, b }: Rgb): string {
  const part = (channel: number): string =>
    clampChannel(channel).toString(16).padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

function relativeLuminance({ r, g, b }: Rgb): number {
  const linear = (channel: number): number => {
    const value = channel / 255;
    return value <= 0.03928
      ? value / 12.92
      : Math.pow((value + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

export function contrastRatio(foreground: string, background: string): number {
  const first = relativeLuminance(hexToRgb(foreground));
  const second = relativeLuminance(hexToRgb(background));
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}

export type ContrastLevel = "AAA" | "AA" | "AA Large" | "Fail";

export function contrastLevel(
  foreground: string,
  background: string,
  largeText = false,
): ContrastLevel {
  const ratio = contrastRatio(foreground, background);
  if (ratio >= 7) return "AAA";
  if (ratio >= 4.5) return "AA";
  if (largeText && ratio >= 3) return "AA Large";
  return "Fail";
}

export function suggestedForeground(background: string): string {
  const dark = contrastRatio("#0a0a0b", background);
  const light = contrastRatio("#f5f5f6", background);
  return dark >= light ? "#0a0a0b" : "#f5f5f6";
}
