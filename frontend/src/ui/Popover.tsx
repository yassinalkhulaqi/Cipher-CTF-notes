import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cx } from "./componentUtils";

export type PopoverPlacement = "top" | "bottom" | "left" | "right";

export interface PopoverProps {
  trigger: ReactNode;
  children: ReactNode;
  placement?: PopoverPlacement;
  className?: string;
}

export function Popover({
  trigger,
  children,
  placement = "bottom",
  className,
}: PopoverProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={root} className={cx("ui-popover", className)}>
      <button
        type="button"
        className="ui-popover__trigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((current) => !current)}
      >
        {trigger}
      </button>
      {open ? (
        <div
          id={panelId}
          role="dialog"
          className={cx("ui-popover__panel", `is-${placement}`)}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
