import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cx } from "../lib/ux";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      loading = false,
      icon,
      block = false,
      className,
      type = "button",
      disabled,
      children,
      ...rest
    },
    ref,
  ) {
    return (
      <button
        {...rest}
        ref={ref}
        type={type}
        className={cx(
          "ui-btn",
          `ui-btn--${variant}`,
          `ui-btn--${size}`,
          block && "ui-btn--block",
          loading && "ui-btn--loading",
          className,
        )}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
      >
        {icon ? (
          <span className="ui-btn__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        {children ? <span className="ui-btn__label">{children}</span> : null}
      </button>
    );
  },
);
