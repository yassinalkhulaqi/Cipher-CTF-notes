import { useCallback, useRef, useState } from "react";

interface TooltipState {
  label: string;
  x: number;
  y: number;
}

export function useTooltip() {
  const [tip, setTip] = useState<TooltipState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((label: string, x: number, y: number) => {
    if (timer.current) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    setTip({ label, x, y });
  }, []);

  const hide = useCallback(() => {
    if (timer.current) {
      window.clearTimeout(timer.current);
    }
    timer.current = window.setTimeout(() => {
      setTip(null);
      timer.current = null;
    }, 120);
  }, []);

  return { tip, show, hide };
}
