import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function readPreference(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia(QUERY).matches;
}

/** Tracks the user's reduced-motion preference and reacts to live changes. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(readPreference);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const list = window.matchMedia(QUERY);
    const update = (event: MediaQueryListEvent): void =>
      setReduced(event.matches);
    setReduced(list.matches);
    if (typeof list.addEventListener === "function") {
      list.addEventListener("change", update);
      return () => list.removeEventListener("change", update);
    }
    list.addListener(update);
    return () => list.removeListener(update);
  }, []);

  return reduced;
}

/** Collapses an animation duration to zero when reduced motion is requested. */
export function motionDuration(ms: number, reduced: boolean): number {
  return reduced ? 0 : ms;
}
