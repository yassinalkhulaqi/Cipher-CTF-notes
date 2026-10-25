import { Ban, CheckCircle2, Circle, CircleDot } from "lucide-react";
import type { Status } from "../lib/types";
import { STATUS_LABEL } from "../lib/constants";

const ICONS = {
  todo: Circle,
  active: CircleDot,
  done: CheckCircle2,
  blocked: Ban,
} as const;

export function StatusIcon({
  status,
  className = "",
  label,
}: {
  status: Status;
  className?: string;
  label?: string;
}) {
  const Icon = ICONS[status] ?? Circle;
  return (
    <Icon
      className={`status-glyph ${status} ${className}`.trim()}
      aria-hidden={label ? undefined : true}
      aria-label={label}
    />
  );
}

export function StatusText({ status }: { status: Status }) {
  return (
    <>
      <StatusIcon status={status} />
      {STATUS_LABEL[status]}
    </>
  );
}
