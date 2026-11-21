import { useId, useState, type ReactNode } from "react";
import { cx } from "./componentUtils";

export interface AccordionItem {
  id: string;
  title: string;
  content: ReactNode;
  disabled?: boolean;
}

export interface AccordionProps {
  items: AccordionItem[];
  defaultOpen?: string;
  allowMultiple?: boolean;
  className?: string;
}

export function Accordion({
  items,
  defaultOpen,
  allowMultiple = false,
  className,
}: AccordionProps) {
  const baseId = useId();
  const [open, setOpen] = useState<string[]>(
    defaultOpen ? [defaultOpen] : [],
  );

  const toggle = (id: string): void => {
    setOpen((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      return allowMultiple ? [...current, id] : [id];
    });
  };

  if (items.length === 0) {
    return <div className="ui-accordion__empty">No sections available.</div>;
  }

  return (
    <div className={cx("ui-accordion", className)}>
      {items.map((item) => {
        const expanded = open.includes(item.id);
        const buttonId = `${baseId}-${item.id}-button`;
        const panelId = `${baseId}-${item.id}-panel`;
        return (
          <section className="ui-accordion__item" key={item.id}>
            <h3 className="ui-accordion__heading">
              <button
                type="button"
                id={buttonId}
                className="ui-accordion__trigger"
                aria-expanded={expanded}
                aria-controls={panelId}
                disabled={item.disabled}
                onClick={() => toggle(item.id)}
              >
                <span className="ui-accordion__title">{item.title}</span>
                <span
                  className={cx(
                    "ui-accordion__chevron",
                    expanded && "is-open",
                  )}
                  aria-hidden="true"
                >
                  ⌄
                </span>
              </button>
            </h3>
            <div
              id={panelId}
              role="region"
              aria-labelledby={buttonId}
              hidden={!expanded}
              className="ui-accordion__panel"
            >
              {item.content}
            </div>
          </section>
        );
      })}
    </div>
  );
}
