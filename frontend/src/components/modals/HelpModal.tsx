import { useMemo, useState } from "react";
import { Keyboard, Search } from "lucide-react";
import { SHORTCUT_GROUPS } from "../../lib/shortcuts";
import { modLabel } from "../../lib/utils";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function HelpModal() {
  const closeModal = useUiStore((state) => state.closeModal);
  const [filter, setFilter] = useState("");

  const groups = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return SHORTCUT_GROUPS;
    return SHORTCUT_GROUPS.map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        `${item.label} ${item.detail ?? ""}`.toLowerCase().includes(needle),
      ),
    })).filter((group) => group.items.length > 0);
  }, [filter]);

  return (
    <Modal
      title="Keyboard shortcuts"
      subtitle="Work without leaving the keyboard"
      icon={<Keyboard />}
      className="help-modal"
      footer={
        <>
          <span className="modal-hint">
            On macOS, <kbd>Ctrl</kbd> becomes <kbd>⌘</kbd>.
          </span>
          <span className="grow" />
          <button type="button" className="btn primary" onClick={closeModal}>
            Got it
          </button>
        </>
      }
      label="Keyboard shortcuts"
    >
      <div className="help-filter">
        <div className="sidebar-search" style={{ margin: 0 }}>
          <Search />
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Find a shortcut…"
            spellCheck={false}
            autoComplete="off"
            aria-label="Find a shortcut"
          />
        </div>
      </div>
      <div className="help-grid">
        {groups.map((group) => (
          <section className="help-group" key={group.title}>
            <h3>{group.title}</h3>
            {group.items.map((item) => (
              <div
                className="shortcut-row"
                key={`${group.title}-${item.label}`}
              >
                <div className="sr-copy">
                  <span>{item.label}</span>
                  {item.detail ? <small>{item.detail}</small> : null}
                </div>
                <span className="sr-keys">
                  {item.keys.map((key) => (
                    <kbd key={key}>{key === "Ctrl" ? modLabel() : key}</kbd>
                  ))}
                </span>
              </div>
            ))}
          </section>
        ))}
        {groups.length === 0 ? (
          <div className="empty">
            <Search />
            <div>No shortcuts match “{filter}”.</div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
