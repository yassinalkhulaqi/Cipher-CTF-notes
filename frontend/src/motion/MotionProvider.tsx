import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";
import {
  resolveMotionLevel,
  useMotionStore,
  type MotionLevel,
  type MotionMode,
} from "./preferences";

interface MotionContextValue {
  mode: MotionMode;
  level: MotionLevel;
  enabled: boolean;
  scale: number;
  setMode: (mode: MotionMode) => void;
}

const MotionContext = createContext<MotionContextValue | null>(null);

export function MotionProvider({ children }: { children: ReactNode }) {
  const mode = useMotionStore((state) => state.mode);
  const systemReduced = useMotionStore((state) => state.systemReduced);
  const setMode = useMotionStore((state) => state.setMode);
  const setSystemReduced = useMotionStore((state) => state.setSystemReduced);
  const level = resolveMotionLevel(mode, systemReduced);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setSystemReduced(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, [setSystemReduced]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.motion = level;
    root.dataset.motionMode = mode;
    root.dataset.motionReady = "true";
    root.style.setProperty(
      "--motion-scale",
      level === "off" ? "0" : level === "subtle" ? "0.55" : "1",
    );
  }, [level, mode]);

  const value = useMemo<MotionContextValue>(
    () => ({
      mode,
      level,
      enabled: level !== "off",
      scale: level === "subtle" ? 0.55 : level === "off" ? 0 : 1,
      setMode,
    }),
    [mode, level, setMode],
  );

  return (
    <MotionContext.Provider value={value}>{children}</MotionContext.Provider>
  );
}

export function useMotion(): MotionContextValue {
  const context = useContext(MotionContext);
  if (context) return context;
  return {
    mode: "system",
    level: "full",
    enabled: true,
    scale: 1,
    setMode: () => undefined,
  };
}

export function useMotionLevel(): MotionLevel {
  return useMotion().level;
}

export function useReducedMotion(): boolean {
  return !useMotion().enabled;
}
