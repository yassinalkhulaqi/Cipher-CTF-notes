import type { ReactNode } from "react";
import { cx } from "../lib/ux";

export interface ToolbarProps {
  label: string;
  children: ReactNode;
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export function Toolbar({
  label,
  children,
  orientation = "horizontal",
  className,
}: ToolbarProps) {
  return (
    <div
      className={cx("ui-toolbar", `ui-toolbar--${orientation}`, className)}
      role="toolbar"
      aria-label={label}
      aria-orientation={orientation}
    >
      {children}
    </div>
  );
}
