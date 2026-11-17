import type { ReactNode } from "react";
import { cx } from "../lib/ux";

export interface UiEmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
}: UiEmptyStateProps) {
  return (
    <div
      className={cx("ui-empty-state", className)}
      role="status"
      aria-live="polite"
    >
      {icon ? (
        <span className="ui-empty-state__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <strong className="ui-empty-state__title">{title}</strong>
      {description ? (
        <p className="ui-empty-state__description">{description}</p>
      ) : null}
      {action ? <div className="ui-empty-state__action">{action}</div> : null}
    </div>
  );
}
