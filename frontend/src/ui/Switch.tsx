import { forwardRef, useId, type ButtonHTMLAttributes } from "react";
import { cx } from "./componentUtils";

export interface SwitchProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label?: string;
  description?: string;
}

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(function Switch(
  { checked, onCheckedChange, label, description, className, disabled, ...rest },
  ref,
) {
  const labelId = useId();
  const descriptionId = useId();

  return (
    <div className={cx("ui-switch-row", className)}>
      <button
        {...rest}
        ref={ref}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={label ? labelId : undefined}
        aria-describedby={description ? descriptionId : undefined}
        disabled={disabled}
        className={cx("ui-switch", checked && "ui-switch--checked")}
        onClick={() => onCheckedChange(!checked)}
      >
        <span className="ui-switch__thumb" aria-hidden="true" />
      </button>
      {label || description ? (
        <span className="ui-switch__text">
          {label ? (
            <span className="ui-switch__label" id={labelId}>
              {label}
            </span>
          ) : null}
          {description ? (
            <span className="ui-switch__description" id={descriptionId}>
              {description}
            </span>
          ) : null}
        </span>
      ) : null}
    </div>
  );
});

export interface SwitchFieldProps {
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function SwitchField({
  label,
  description,
  checked,
  onCheckedChange,
  disabled,
}: SwitchFieldProps) {
  return (
    <fieldset className="ui-switch-field" disabled={disabled}>
      <legend className="ui-switch-field__legend">{label}</legend>
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        description={description}
      />
    </fieldset>
  );
}
