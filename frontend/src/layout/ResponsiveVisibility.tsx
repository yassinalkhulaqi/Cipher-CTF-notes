import type { ReactNode } from "react";
import { breakpointOrder, type Breakpoint } from "./breakpoints";
import { useBreakpoint } from "./useBreakpoint";

export interface ResponsiveVisibilityProps {
  children: ReactNode;
  from?: Breakpoint;
  to?: Breakpoint;
  fallback?: ReactNode;
}

export function ResponsiveVisibility({
  children,
  from,
  to,
  fallback,
}: ResponsiveVisibilityProps) {
  const current = useBreakpoint();
  const index = breakpointOrder.indexOf(current);
  const fromIndex = from ? breakpointOrder.indexOf(from) : 0;
  const toIndex = to ? breakpointOrder.indexOf(to) : breakpointOrder.length - 1;
  const visible = index >= fromIndex && index <= toIndex;

  if (!visible) return fallback ? <>{fallback}</> : null;
  return <>{children}</>;
}
