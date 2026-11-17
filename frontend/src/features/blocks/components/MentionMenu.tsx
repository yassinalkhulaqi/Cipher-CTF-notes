import { memo } from "react";
import { type MentionSuggestion } from "../types";

export interface MentionMenuProps {
  suggestions: MentionSuggestion[];
  activeIndex?: number;
  onSelect: (suggestion: MentionSuggestion) => void;
  onHover: (index: number) => void;
}

export const MentionMenu = memo(function MentionMenu({
  suggestions,
  activeIndex = 0,
  onSelect,
  onHover,
}: MentionMenuProps) {
  if (suggestions.length === 0) return null;
  return (
    <div
      className="mention-menu"
      role="listbox"
      aria-label="Mention suggestions"
    >
      {suggestions.map((suggestion, index) => (
        <button
          aria-selected={index === activeIndex}
          className={`mention-menu__item${index === activeIndex ? " is-active" : ""}`}
          key={`${suggestion.kind}:${suggestion.target}`}
          role="option"
          type="button"
          onMouseEnter={() => onHover(index)}
          onClick={() => onSelect(suggestion)}
        >
          <span className="mention-menu__kind">{suggestion.kind}</span>
          <span className="mention-menu__label">{suggestion.label}</span>
          <span className="mention-menu__target">{suggestion.target}</span>
        </button>
      ))}
    </div>
  );
});

export function mentionMenuLabel(suggestion: MentionSuggestion): string {
  return `@[${suggestion.label}](${suggestion.kind}:${suggestion.target})`;
}
