export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export function parseHex(hex: string): Rgb {
  const clean = hex.replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((char) => char + char)
          .join("")
      : clean;
  const value = Number.parseInt(full, 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

export function toHex({ r, g, b }: Rgb): string {
  const part = (channel: number): string =>
    Math.max(0, Math.min(255, Math.round(channel)))
      .toString(16)
      .padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

export function mix(first: string, second: string, amount: number): string {
  const start = parseHex(first);
  const end = parseHex(second);
  const weight = Math.max(0, Math.min(1, amount));
  return toHex({
    r: start.r + (end.r - start.r) * weight,
    g: start.g + (end.g - start.g) * weight,
    b: start.b + (end.b - start.b) * weight,
  });
}

export function lighten(color: string, amount: number): string {
  return mix(color, "#ffffff", amount);
}

export function darken(color: string, amount: number): string {
  return mix(color, "#000000", amount);
}

export function withAlpha(color: string, alpha: number): string {
  const { r, g, b } = parseHex(color);
  const value = Math.max(0, Math.min(1, alpha));
  return `rgba(${r}, ${g}, ${b}, ${value})`;
}

export function luminance(color: string): number {
  const { r, g, b } = parseHex(color);
  const channel = (value: number): number => {
    const normalized = value / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : Math.pow((normalized + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function isLight(color: string): boolean {
  return luminance(color) > 0.5;
}
