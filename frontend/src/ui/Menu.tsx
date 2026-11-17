import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../lib/ux";

export interface MenuItem {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  shortcut?: string;
  danger?: boolean;
  disabled?: boolean;
  onSelect?: () => void;
}

export interface MenuSeparator {
  type: "separator";
  id?: string;
}

export type MenuEntry = MenuItem | MenuSeparator;

function isSeparator(entry: MenuEntry): entry is MenuSeparator {
  return "type" in entry && entry.type === "separator";
}

export interface MenuProps {
  items: MenuEntry[];
  label: string;
  onClose?: () => void;
  className?: string;
}

export function Menu({ items, label, onClose, className }: MenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      menuRef.current
        ?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')
        ?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const focusableItems = () =>
    Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]:not(:disabled)',
      ) ?? [],
    );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const focusable = focusableItems();
    if (event.key === "Escape" || event.key === "Tab") {
      if (event.key === "Escape") event.preventDefault();
      onClose?.();
      return;
    }
    if (focusable.length === 0) return;

    const index = focusable.indexOf(
      document.activeElement as HTMLButtonElement,
    );
    let next: HTMLButtonElement | undefined;

    if (event.key === "ArrowDown") {
      next = focusable[index < 0 ? 0 : (index + 1) % focusable.length];
    } else if (event.key === "ArrowUp") {
      next =
        focusable[
          index < 0
            ? focusable.length - 1
            : (index - 1 + focusable.length) % focusable.length
        ];
    } else if (event.key === "Home") {
      next = focusable[0];
    } else if (event.key === "End") {
      next = focusable[focusable.length - 1];
    }

    if (next) {
      event.preventDefault();
      next.focus();
    }
  };

  return (
    <div
      ref={menuRef}
      className={cx("ui-menu", className)}
      role="menu"
      aria-label={label}
      onKeyDown={onKeyDown}
    >
      {items.map((entry, index) => {
        if (isSeparator(entry)) {
          return (
            <div
              key={entry.id ?? `separator-${index}`}
              className="ui-menu__separator"
              role="separator"
            />
          );
        }
        return (
          <button
            key={entry.id}
            type="button"
            className={cx(
              "ui-menu__item",
              entry.danger && "ui-menu__item--danger",
            )}
            role="menuitem"
            tabIndex={-1}
            disabled={entry.disabled}
            onClick={() => {
              if (entry.disabled) return;
              entry.onSelect?.();
              onClose?.();
            }}
          >
            {entry.icon ? (
              <span className="ui-menu__icon" aria-hidden="true">
                {entry.icon}
              </span>
            ) : null}
            <span className="ui-menu__label">{entry.label}</span>
            {entry.shortcut ? (
              <kbd className="ui-menu__shortcut">{entry.shortcut}</kbd>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
