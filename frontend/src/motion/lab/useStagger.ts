import { useCallback, useMemo, useState, type CSSProperties } from "react";
import { duration } from "./durations";

export interface StaggerOptions {
  count: number;
  step?: number;
  delay?: number;
}

export interface StaggerApi {
  running: boolean;
  revealed: number;
  start: () => void;
  reset: () => void;
  styleFor: (index: number) => CSSProperties;
}

export function useStagger({
  count,
  step = 60,
  delay = 0,
}: StaggerOptions): StaggerApi {
  const [running, setRunning] = useState(false);

  const start = useCallback((): void => setRunning(true), []);
  const reset = useCallback((): void => setRunning(false), []);

  const revealed = useMemo(() => (running ? count : 0), [running, count]);

  const styleFor = useCallback(
    (index: number): CSSProperties => ({
      transitionDelay: `${delay + index * step}ms`,
      transitionDuration: `${duration.normal}ms`,
    }),
    [delay, step],
  );

  return { running, revealed, start, reset, styleFor };
}
