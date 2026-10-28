export type SpringConfig = {
  stiffness: number;
  damping: number;
  mass: number;
};

export const DURATION = {
  instant: 70,
  fast: 140,
  base: 220,
  slow: 340,
  slower: 520,
  cinematic: 760,
} as const;

export const EASE = {
  out: "cubic-bezier(0.22, 1, 0.36, 1)",
  outSoft: "cubic-bezier(0.16, 1, 0.3, 1)",
  inOut: "cubic-bezier(0.65, 0, 0.35, 1)",
  spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
  sharp: "cubic-bezier(0.4, 0, 0.2, 1)",
} as const;

export const SPRING = {
  snappy: { stiffness: 520, damping: 34, mass: 0.7 },
  gentle: { stiffness: 220, damping: 26, mass: 1 },
  bouncy: { stiffness: 420, damping: 20, mass: 0.9 },
  heavy: { stiffness: 150, damping: 24, mass: 1.4 },
  counter: { stiffness: 120, damping: 22, mass: 1 },
  follow: { stiffness: 150, damping: 25, mass: 0.8 },
} satisfies Record<string, SpringConfig>;

export const STAGGER = {
  tight: 18,
  base: 32,
  loose: 52,
  wide: 70,
} as const;

export const DISTANCE = {
  hairline: 2,
  nudge: 6,
  base: 12,
  lift: 18,
  hero: 32,
} as const;

export const SCALE = {
  press: 0.965,
  enter: 0.985,
  pop: 1.02,
} as const;
