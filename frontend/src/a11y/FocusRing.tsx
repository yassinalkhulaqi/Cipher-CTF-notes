import { useCallback, type FocusEvent, type ReactNode } from "react";

export interface FocusRingProps {
  children: ReactNode;
  className?: string;
  onFocusChange?: (focused: boolean) => void;
}

/** Adds a keyboard-visible focus indicator around arbitrary content. */
export function FocusRing({
  children,
  className = "",
  onFocusChange,
}: FocusRingProps) {
  const handleFocus = useCallback(
    (event: FocusEvent<HTMLDivElement>): void => {
      if (event.target === event.currentTarget) onFocusChange?.(true);
    },
    [onFocusChange],
  );
  const handleBlur = useCallback(
    (event: FocusEvent<HTMLDivElement>): void => {
      if (event.target === event.currentTarget) onFocusChange?.(false);
    },
    [onFocusChange],
  );

  return (
    <div
      className={`a11y-focus-ring ${className}`.trim()}
      tabIndex={0}
      onFocus={handleFocus}
      onBlur={handleBlur}
    >
      {children}
    </div>
  );
}
