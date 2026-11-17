import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { cx } from "../lib/ux";

export interface TabItem {
  id: string;
  label: ReactNode;
  content?: ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  label: string;
  value?: string;
  defaultValue?: string;
  onChange?: (id: string) => void;
  className?: string;
}

function firstEnabledId(items: TabItem[]): string | null {
  return items.find((item) => !item.disabled)?.id ?? null;
}

export function Tabs({
  items,
  label,
  value,
  defaultValue,
  onChange,
  className,
}: TabsProps) {
  const baseId = useId();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [internalValue, setInternalValue] = useState<string | null>(
    () => value ?? defaultValue ?? firstEnabledId(items),
  );

  useEffect(() => {
    if (value !== undefined) return;
    const current = internalValue;
    const valid =
      current !== null &&
      items.some((item) => item.id === current && !item.disabled);
    if (valid) return;
    const fallback = firstEnabledId(items);
    if (fallback !== null) setInternalValue(fallback);
  }, [items, value, internalValue]);

  const activeId = value ?? internalValue;
  const tabbableId = items.some(
    (item) => item.id === activeId && !item.disabled,
  )
    ? activeId
    : firstEnabledId(items);

  const activate = (id: string) => {
    if (value === undefined) setInternalValue(id);
    onChange?.(id);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const enabled = items.filter((item) => !item.disabled);
    if (enabled.length === 0) return;

    const index = enabled.findIndex((item) => item.id === activeId);
    let nextIndex: number | null = null;

    if (event.key === "ArrowRight") {
      nextIndex = index < 0 ? 0 : (index + 1) % enabled.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex =
        index < 0
          ? enabled.length - 1
          : (index - 1 + enabled.length) % enabled.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = enabled.length - 1;
    }

    if (nextIndex === null) return;
    event.preventDefault();
    const next = enabled[nextIndex];
    if (!next) return;
    tabRefs.current[next.id]?.focus();
    activate(next.id);
  };

  return (
    <div className={cx("ui-tabs", className)}>
      <div className="ui-tabs__list" role="tablist" aria-label={label}>
        {items.map((item, index) => {
          const selected = item.id === activeId;
          const tabId = `${baseId}-tab-${index}`;
          const panelId = `${baseId}-panel-${index}`;
          return (
            <button
              key={item.id}
              ref={(node) => {
                tabRefs.current[item.id] = node;
              }}
              type="button"
              className={cx("ui-tabs__tab", selected && "ui-tabs__tab--active")}
              id={tabId}
              role="tab"
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={item.id === tabbableId ? 0 : -1}
              disabled={item.disabled}
              onClick={() => activate(item.id)}
              onKeyDown={onKeyDown}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item, index) => {
        const selected = item.id === activeId;
        const tabId = `${baseId}-tab-${index}`;
        const panelId = `${baseId}-panel-${index}`;
        return (
          <div
            key={item.id}
            className="ui-tabs__panel"
            id={panelId}
            role="tabpanel"
            aria-labelledby={tabId}
            hidden={!selected}
            tabIndex={selected ? 0 : -1}
          >
            {item.content}
          </div>
        );
      })}
    </div>
  );
}
