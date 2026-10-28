import { create } from "zustand";

export type MotionMode = "system" | "full" | "subtle" | "off";
export type MotionLevel = "full" | "subtle" | "off";

export const MOTION_STORAGE_KEY = "redscribe.motion.mode";

export const MOTION_MODE_LABEL: Record<MotionMode, string> = {
  system: "System",
  full: "Full",
  subtle: "Subtle",
  off: "Off",
};

export const MOTION_MODE_DETAIL: Record<MotionMode, string> = {
  system: "Follow the operating system's reduced-motion preference.",
  full: "Every spring, parallax, and flourish at full strength.",
  subtle: "Shorter travel, softer springs, same responsiveness.",
  off: "Instant state changes with no movement.",
};

export function normalizeMotionMode(value: unknown): MotionMode {
  if (value === "system" || value === "full" || value === "subtle" || value === "off") {
    return value;
  }
  return "system";
}

function readStoredMode(): MotionMode {
  try {
    return normalizeMotionMode(window.localStorage.getItem(MOTION_STORAGE_KEY));
  } catch {
    return "system";
  }
}

function systemPrefersReduced(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface MotionState {
  mode: MotionMode;
  systemReduced: boolean;
  setMode: (mode: MotionMode) => void;
  setSystemReduced: (reduced: boolean) => void;
}

export const useMotionStore = create<MotionState>()((set) => ({
  mode: readStoredMode(),
  systemReduced: systemPrefersReduced(),
  setMode: (mode) => {
    const next = normalizeMotionMode(mode);
    try {
      window.localStorage.setItem(MOTION_STORAGE_KEY, next);
    } catch {
      undefined;
    }
    set({ mode: next });
  },
  setSystemReduced: (reduced) => set({ systemReduced: reduced }),
}));

export function resolveMotionLevel(
  mode: MotionMode,
  systemReduced: boolean,
): MotionLevel {
  if (mode === "off") return "off";
  if (mode === "subtle") return "subtle";
  if (mode === "full") return "full";
  return systemReduced ? "off" : "full";
}

export function currentMotionLevel(): MotionLevel {
  const state = useMotionStore.getState();
  return resolveMotionLevel(state.mode, state.systemReduced);
}

export function motionEnabled(): boolean {
  return currentMotionLevel() !== "off";
}

export function motionScale(): number {
  const level = currentMotionLevel();
  if (level === "off") return 0;
  if (level === "subtle") return 0.55;
  return 1;
}

export function motionDuration(duration: number): number {
  return Math.max(0, Math.round(duration * motionScale()));
}
