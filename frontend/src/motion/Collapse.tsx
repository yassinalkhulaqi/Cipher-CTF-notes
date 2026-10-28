import type { ReactNode } from "react";

interface CollapseProps {
  open: boolean;
  children: ReactNode;
  className?: string;
}

export function Collapse({ open, children, className = "" }: CollapseProps) {
  return (
    <div
      className={`collapse ${open ? "is-open" : ""} ${className}`.trim()}
      data-collapse={open ? "open" : "closed"}
    >
      <div className="collapse-inner">{children}</div>
    </div>
  );
}
