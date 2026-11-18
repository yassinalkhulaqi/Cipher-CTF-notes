import { memo } from "react";
import { filterSlashCommands } from "../slashCommands";
import { type SlashCommand } from "../types";

export interface SlashMenuProps {
  query: string;
  activeIndex?: number;
  onSelect: (command: SlashCommand) => void;
  onHover: (index: number) => void;
}

export const SlashMenu = memo(function SlashMenu({
  query,
  activeIndex = 0,
  onSelect,
  onHover,
}: SlashMenuProps) {
  const commands = filterSlashCommands(query);
  if (commands.length === 0) return null;
  return (
    <div className="slash-menu" role="listbox" aria-label="Block commands">
      {commands.map((command, index) => (
        <button
          aria-selected={index === activeIndex}
          className={`slash-menu__item${index === activeIndex ? " is-active" : ""}`}
          key={command.id}
          role="option"
          type="button"
          onMouseEnter={() => onHover(index)}
          onClick={() => onSelect(command)}
        >
          <span className="slash-menu__title">{command.title}</span>
          <span className="slash-menu__description">{command.description}</span>
        </button>
      ))}
    </div>
  );
});

export function slashMenuCount(query: string): number {
  return filterSlashCommands(query).length;
}
