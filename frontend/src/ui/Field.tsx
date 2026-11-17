import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { cx } from "../lib/ux";

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  containerClassName?: string;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  {
    label,
    hint,
    error,
    containerClassName,
    className,
    id,
    "aria-describedby": describedBy,
    "aria-invalid": ariaInvalid,
    ...rest
  },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedByIds = [describedBy, hintId, errorId]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={cx(
        "ui-field",
        !!error && "ui-field--error",
        containerClassName,
      )}
    >
      <label className="ui-field__label" htmlFor={inputId}>
        {label}
      </label>
      <input
        {...rest}
        ref={ref}
        id={inputId}
        className={cx("ui-field__input", className)}
        aria-invalid={ariaInvalid ?? (error ? true : undefined)}
        aria-describedby={describedByIds || undefined}
      />
      {hint ? (
        <span className="ui-field__hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="ui-field__error" id={errorId} role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
});
