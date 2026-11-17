import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cx } from "../lib/ux";

export type IconButtonVariant = "ghost" | "solid" | "danger";
export type IconButtonSize = "sm" | "md";

export interface IconButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  icon: ReactNode;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      label,
      icon,
      variant = "ghost",
      size = "md",
      className,
      type = "button",
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
          "ui-icon-btn",
          `ui-icon-btn--${variant}`,
          `ui-icon-btn--${size}`,
          className,
        )}
        aria-label={label}
        title={rest.title ?? label}
      >
        <span aria-hidden="true">{icon}</span>
      </button>
    );
  },
);
