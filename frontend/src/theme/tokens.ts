export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
  "3xl": 48,
} as const;

export type SpacingToken = keyof typeof spacing;

export const radius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  full: 999,
} as const;

export type RadiusToken = keyof typeof radius;

export const typography = {
  size: {
    xs: 10,
    sm: 11,
    md: 12,
    base: 13,
    lg: 14,
    xl: 16,
    "2xl": 18,
    "3xl": 21,
  },
  weight: {
    normal: 450,
    medium: 520,
    semibold: 600,
    bold: 650,
  },
  leading: {
    none: 1.2,
    tight: 1.35,
    base: 1.55,
    relaxed: 1.7,
  },
} as const;

export const elevation = {
  sm: "0 1px 2px rgba(0, 0, 0, 0.18)",
  md: "0 4px 12px rgba(0, 0, 0, 0.22)",
  lg: "0 12px 32px rgba(0, 0, 0, 0.32)",
  xl: "0 24px 64px rgba(0, 0, 0, 0.42)",
} as const;

export type ElevationToken = keyof typeof elevation;

export const zIndex = {
  base: 0,
  raised: 10,
  sticky: 100,
  dropdown: 200,
  modal: 300,
  toast: 400,
  overlay: 1000,
} as const;

export type ZIndexToken = keyof typeof zIndex;

export function spacingPx(token: SpacingToken): string {
  return `${spacing[token]}px`;
}

export function radiusPx(token: RadiusToken): string {
  return `${radius[token]}px`;
}
