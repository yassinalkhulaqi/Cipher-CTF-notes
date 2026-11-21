import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./componentUtils";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "success"
  | "warning"
  | "danger"
  | "info";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  dot?: boolean;
  outline?: boolean;
  children?: ReactNode;
}

export function Badge({
  tone = "neutral",
  dot = false,
  outline = false,
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      {...rest}
      className={cx(
        "ui-badge",
        `ui-badge--${tone}`,
        outline && "ui-badge--outline",
        className,
      )}
    >
      {dot ? <span className="ui-badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export interface CountBadgeProps {
  count: number;
  max?: number;
  tone?: BadgeTone;
  label: string;
}

export function CountBadge({
  count,
  max = 99,
  tone = "accent",
  label,
}: CountBadgeProps) {
  const text = count > max ? `${max}+` : String(count);
  return (
    <Badge tone={tone} aria-label={`${label}: ${count}`}>
      {text}
    </Badge>
  );
}

export function BadgeGroup({ children }: { children: ReactNode }) {
  return <div className="ui-badge-group">{children}</div>;
}
