import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cx } from "../lib/ux";

export interface EmptyStateAction {
  label: string;
  onClick: () => void;
  variant?: "primary" | "ghost" | "subtle";
  icon?: ReactNode;
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  actions?: EmptyStateAction[];
  compact?: boolean;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  compact = false,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cx(
        "empty-state",
        compact && "empty-state--compact",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <span className="empty-state__icon" aria-hidden="true">
        <Icon />
      </span>
      <strong className="empty-state__title">{title}</strong>
      {description ? (
        <p className="empty-state__description">{description}</p>
      ) : null}
      {actions && actions.length > 0 ? (
        <div className="empty-state__actions">
          {actions.map((action, index) => (
            <button
              key={`${action.label}-${index}`}
              type="button"
              className={`btn ${action.variant ?? "ghost"} sm`}
              onClick={action.onClick}
            >
              {action.icon}
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
