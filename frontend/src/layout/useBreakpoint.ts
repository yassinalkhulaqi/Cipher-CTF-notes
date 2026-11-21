import { useEffect, useState } from "react";
import { breakpointOrder, breakpoints, type Breakpoint } from "./breakpoints";

function currentWidth(): number {
  return typeof window === "undefined" ? 1440 : window.innerWidth;
}

function keyFor(width: number): Breakpoint {
  let key: Breakpoint = "xs";
  for (const candidate of breakpointOrder) {
    if (width >= breakpoints[candidate]) key = candidate;
  }
  return key;
}

export function useWindowWidth(): number {
  const [width, setWidth] = useState<number>(currentWidth);

  useEffect(() => {
    const update = (): void => setWidth(window.innerWidth);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return width;
}

export function useBreakpoint(): Breakpoint {
  return keyFor(useWindowWidth());
}

export function useIsBelow(breakpoint: Breakpoint): boolean {
  const width = useWindowWidth();
  return width < breakpoints[breakpoint];
}

export function useIsAbove(breakpoint: Breakpoint): boolean {
  const width = useWindowWidth();
  return width >= breakpoints[breakpoint];
}
