import type { LucideIcon } from "lucide-react";

interface ToolButtonProps {
  icon: LucideIcon;
  label: string;
  shortcut?: string;
  onClick: () => void;
}

/** Icon-only toolbar button with a tooltip and aria label. */
export function ToolButton({
  icon: Icon,
  label,
  shortcut,
  onClick,
}: ToolButtonProps) {
  return (
    <button
      type="button"
      className="tool-btn"
      onClick={onClick}
      title={`${label}${shortcut ? ` (${shortcut})` : ""}`}
      aria-label={label}
    >
      <Icon />
    </button>
  );
}
