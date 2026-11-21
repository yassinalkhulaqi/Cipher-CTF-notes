import type { ReactNode } from "react";

export interface LiveRegionProps {
  children?: ReactNode;
  politeness?: "polite" | "assertive";
  atomic?: boolean;
  role?: "status" | "alert" | "log";
}

/** A visually hidden live region for announcing dynamic state changes. */
export function LiveRegion({
  children,
  politeness = "polite",
  atomic = true,
  role = "status",
}: LiveRegionProps) {
  return (
    <div
      className="a11y-live-region"
      role={role}
      aria-live={politeness}
      aria-atomic={atomic}
    >
      {children}
    </div>
  );
}
