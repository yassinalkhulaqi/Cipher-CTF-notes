import type { ReactNode } from "react";
import { integrityLabel, integrityTone } from "../format";
import type { IntegrityReport } from "../types";

interface IntegrityBadgeProps {
  report?: IntegrityReport;
  compact?: boolean;
  icon?: ReactNode;
}

export function IntegrityBadge({
  report,
  compact = false,
  icon,
}: IntegrityBadgeProps) {
  const state = report?.state ?? "unknown";
  const tone = integrityTone(report);
  return (
    <span
      className={`ev-badge ev-badge--${tone} ${compact ? "ev-badge--compact" : ""}`}
      title={
        report
          ? `${integrityLabel(state)} · SHA-256 verified`
          : "Integrity not checked"
      }
    >
      {icon}
      <span>{integrityLabel(state)}</span>
    </span>
  );
}
