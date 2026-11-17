import type { ReactNode } from "react";
import { cx } from "../lib/ux";

export type BannerTone = "info" | "success" | "warning" | "danger";

export interface BannerProps {
  tone?: BannerTone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
  dismissLabel?: string;
  role?: "status" | "alert" | "note";
  className?: string;
}

export function Banner({
  tone = "info",
  title,
  children,
  action,
  onDismiss,
  dismissLabel = "Dismiss",
  role,
  className,
}: BannerProps) {
  const resolvedRole =
    role ?? (tone === "danger" || tone === "warning" ? "alert" : "status");

  return (
    <div
      className={cx("ui-banner", `ui-banner--${tone}`, className)}
      role={resolvedRole}
    >
      <div className="ui-banner__content">
        {title ? <strong className="ui-banner__title">{title}</strong> : null}
        {children ? <div className="ui-banner__body">{children}</div> : null}
      </div>
      {action ? <div className="ui-banner__action">{action}</div> : null}
      {onDismiss ? (
        <button
          type="button"
          className="ui-banner__dismiss"
          onClick={onDismiss}
          aria-label={dismissLabel}
        >
          <span aria-hidden="true">×</span>
        </button>
      ) : null}
    </div>
  );
}
