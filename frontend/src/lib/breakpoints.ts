/**
 * Canonical breakpoint scale for the app.
 *
 * CSS media queries cannot consume CSS custom properties, so @media rules and
 * these JavaScript queries are kept in sync by convention and documented in
 * `styles/tokens.css` and `docs/DESIGN_SYSTEM.md`:
 *
 *   xs: 420px   compact phones, single-column dialogs
 *   sm: 560px   large phones, two-pane collapse
 *   md: 720px   tablets, mobile sidebar threshold
 *   lg: 920px   small laptops, inspector overlays the workspace
 *   xl: 1180px  default desktop density
 */
export const BREAKPOINTS = {
  xs: 420,
  sm: 560,
  md: 720,
  lg: 920,
  xl: 1180,
} as const;

export type Breakpoint = keyof typeof BREAKPOINTS;

export function maxWidthQuery(breakpoint: Breakpoint): string {
  return `(max-width: ${BREAKPOINTS[breakpoint]}px)`;
}
