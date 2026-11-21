export type EasingFunction = (progress: number) => number;

const easeOutBack = (t: number): number => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};

const easeOutElastic = (t: number): number => {
  if (t === 0 || t === 1) return t;
  const c4 = (2 * Math.PI) / 3;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
};

export const easing = {
  linear: (t: number): number => t,
  easeIn: (t: number): number => t * t,
  easeOut: (t: number): number => 1 - Math.pow(1 - t, 2),
  easeInOut: (t: number): number =>
    t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
  easeOutCubic: (t: number): number => 1 - Math.pow(1 - t, 3),
  easeOutQuint: (t: number): number => 1 - Math.pow(1 - t, 5),
  easeOutExpo: (t: number): number =>
    t === 1 ? 1 : 1 - Math.pow(2, -10 * t),
  easeOutBack,
  easeOutElastic,
} satisfies Record<string, EasingFunction>;

export type EasingName = keyof typeof easing;

export function resolveEasing(name: EasingName): EasingFunction {
  return easing[name];
}

export function clampProgress(value: number): number {
  return Math.max(0, Math.min(1, value));
}
