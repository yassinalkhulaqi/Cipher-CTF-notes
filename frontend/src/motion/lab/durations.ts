export const duration = {
  instant: 0,
  fast: 120,
  normal: 200,
  slow: 320,
  deliberate: 480,
} as const;

export type DurationName = keyof typeof duration;

export function cssDuration(name: DurationName, reduced = false): string {
  return `${reduced ? 0 : duration[name]}ms`;
}

export const cssEasing = {
  standard: "cubic-bezier(0.2, 0.7, 0.2, 1)",
  entrance: "cubic-bezier(0.16, 1, 0.3, 1)",
  exit: "cubic-bezier(0.4, 0, 1, 1)",
  spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
} as const;

export type CssEasingName = keyof typeof cssEasing;

export function staggerDelay(index: number, step = 60, base = 0): string {
  return `${base + index * step}ms`;
}
