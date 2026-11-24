/** Layout strategy switcher with keyboard-accessible controls. */

import type { LayoutKind } from "./types";
import { LAYOUT_HINTS, LAYOUT_KINDS, LAYOUT_LABELS } from "./types";

export interface LayoutSwitcherProps {
  value: LayoutKind;
  onChange: (value: LayoutKind) => void;
  disabled?: boolean;
}

export function LayoutSwitcher({
  value,
  onChange,
  disabled = false,
}: LayoutSwitcherProps) {
  return (
    <div
      className="gw-layout-switcher"
      data-testid="gw-layout-switcher"
      role="group"
      aria-label="Graph layout strategy"
    >
      {LAYOUT_KINDS.map((kind) => (
        <button
          key={kind}
          type="button"
          className="gw-layout-button"
          data-layout={kind}
          data-active={kind === value}
          aria-pressed={kind === value}
          aria-label={`${LAYOUT_LABELS[kind]} layout: ${LAYOUT_HINTS[kind]}`}
          title={LAYOUT_HINTS[kind]}
          disabled={disabled}
          onClick={() => onChange(kind)}
        >
          <span className="gw-layout-button__label">{LAYOUT_LABELS[kind]}</span>
          <span className="gw-layout-button__hint">{LAYOUT_HINTS[kind]}</span>
        </button>
      ))}
    </div>
  );
}
