export const breakpoints = {
  xs: 360,
  sm: 480,
  md: 640,
  lg: 900,
  xl: 1200,
  "2xl": 1600,
} as const;

export type Breakpoint = keyof typeof breakpoints;

export const breakpointOrder: Breakpoint[] = [
  "xs",
  "sm",
  "md",
  "lg",
  "xl",
  "2xl",
];

export function minWidth(query: Breakpoint): string {
  return `(min-width: ${breakpoints[query]}px)`;
}

export function maxWidth(query: Breakpoint): string {
  return `(max-width: ${breakpoints[query] - 1}px)`;
}

export function mediaQuery(min: Breakpoint, max?: Breakpoint): string {
  if (!max) return minWidth(min);
  return `${minWidth(min)} and ${maxWidth(max)}`;
}

export type BreakpointMap<T> = Partial<Record<Breakpoint, T>>;

export function resolveBreakpointValue<T>(
  values: BreakpointMap<T>,
  width: number,
  fallback: T,
): T {
  let result = fallback;
  for (const key of breakpointOrder) {
    if (width >= breakpoints[key] && values[key] !== undefined) {
      result = values[key] as T;
    }
  }
  return result;
}
