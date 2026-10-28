import { useEffect, useState } from "react";
import { DURATION } from "./config";
import { motionDuration } from "./preferences";

export interface PresenceState {
  mounted: boolean;
  exiting: boolean;
}

export function usePresence(
  visible: boolean,
  duration = DURATION.base,
): PresenceState {
  const [mounted, setMounted] = useState(visible);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      setExiting(false);
      return;
    }
    if (!mounted) return;
    setExiting(true);
    const timer = window.setTimeout(() => {
      setMounted(false);
      setExiting(false);
    }, motionDuration(duration));
    return () => window.clearTimeout(timer);
  }, [visible, mounted, duration]);

  return { mounted, exiting };
}
