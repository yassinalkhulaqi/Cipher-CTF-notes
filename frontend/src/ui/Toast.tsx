import type { ReactNode } from "react";
import { cx } from "../lib/ux";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastProps {
  tone?: ToastTone;
  title?: ReactNode;
  children?: ReactNode;
  onDismiss?: () => void;
  dismissLabel?: string;
  className?: string;
}

export interface ToastRegionProps {
  label?: string;
  children?: ReactNode;
  className?: string;
}

function toastRole(tone: ToastTone): "status" | "alert" {
  return tone === "danger" || tone === "warning" ? "alert" : "status";
}

export function Toast({
  tone = "info",
  title,
  children,
  onDismiss,
  dismissLabel = "Dismiss notification",
  className,
}: ToastProps) {
  return (
    <div
      className={cx("ui-toast", `ui-toast--${tone}`, className)}
      role={toastRole(tone)}
      aria-live={tone === "danger" ? "assertive" : "polite"}
      aria-atomic="true"
    >
      <div className="ui-toast__content">
        {title ? <strong className="ui-toast__title">{title}</strong> : null}
        {children ? <div className="ui-toast__body">{children}</div> : null}
      </div>
      {onDismiss ? (
        <button
          type="button"
          className="ui-toast__dismiss"
          onClick={onDismiss}
          aria-label={dismissLabel}
        >
          <span aria-hidden="true">×</span>
        </button>
      ) : null}
    </div>
  );
}

export function ToastRegion({
  label = "Notifications",
  children,
  className,
}: ToastRegionProps) {
  return (
    <div className={cx("ui-toast-region", className)} aria-label={label}>
      {children}
    </div>
  );
}
