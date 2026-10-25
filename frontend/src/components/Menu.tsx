import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import type { LucideIcon } from "lucide-react";

export interface MenuAction {
  label: string;
  icon?: LucideIcon;
  shortcut?: string;
  danger?: boolean;
  disabled?: boolean;
  onSelect: () => void;
}

export type MenuEntry = MenuAction | "separator";

interface MenuProps {
  x: number;
  y: number;
  items: MenuEntry[];
  onClose: () => void;
  label?: string;
}

export function Menu({ x, y, items, onClose, label = "Actions" }: MenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const rect = menu.getBoundingClientRect();
    const left = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8));
    const top = Math.max(8, Math.min(y, window.innerHeight - rect.height - 8));
    setPosition({ left, top });
  }, [x, y, items.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    const timer = window.setTimeout(() => {
      menuRef.current
        ?.querySelector<HTMLButtonElement>(".menu-item:not(:disabled)")
        ?.focus();
    }, 10);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        ".menu-item:not(:disabled)",
      ) ?? [],
    );
    if (!items.length) return;
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length]?.focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      items[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      items[items.length - 1]?.focus();
    } else if (event.key === "Tab") {
      onClose();
    }
  };

  return createPortal(
    <>
      <div
        className="menu-backdrop"
        onMouseDown={onClose}
        onContextMenu={(event) => event.preventDefault()}
      />
      <div
        ref={menuRef}
        className="context-menu"
        role="menu"
        aria-label={label}
        style={{ left: position.left, top: position.top }}
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={onMenuKeyDown}
      >
        {items.map((item, index) => {
          if (item === "separator") {
            return <div className="menu-sep" key={`separator-${index}`} />;
          }
          const Icon = item.icon;
          return (
            <button
              key={`${item.label}-${index}`}
              type="button"
              className={`menu-item ${item.danger ? "danger" : ""}`}
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                onClose();
                item.onSelect();
              }}
            >
              {Icon ? <Icon /> : null}
              <span className="menu-label">{item.label}</span>
              {item.shortcut ? (
                <span className="menu-key">{item.shortcut}</span>
              ) : null}
            </button>
          );
        })}
      </div>
    </>,
    document.body,
  );
}
