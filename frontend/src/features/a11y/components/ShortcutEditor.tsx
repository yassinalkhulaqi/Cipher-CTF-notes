import { useMemo, useState } from "react";
import { PLATFORM_LABEL } from "../config";
import {
  bindingId,
  filterShortcuts,
  formatBinding,
  groupShortcuts,
  normalizeBinding,
  parseBinding,
} from "../pure";
import type { Platform, ShortcutBinding } from "../types";

export interface ShortcutEditorProps {
  shortcuts: readonly ShortcutBinding[];
  onOverride: (action: string, keys: string[]) => void;
}

export function ShortcutEditor({ shortcuts, onOverride }: ShortcutEditorProps) {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<Platform>("desktop");
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const filtered = useMemo(
    () => filterShortcuts(shortcuts, query),
    [shortcuts, query],
  );
  const groups = useMemo(() => groupShortcuts(filtered), [filtered]);

  const draftFor = (shortcut: ShortcutBinding): string =>
    drafts[shortcut.action] ?? normalizeBinding(shortcut.keys);

  const apply = (shortcut: ShortcutBinding): void => {
    const keys = parseBinding(draftFor(shortcut));
    if (keys.length === 0) return;
    onOverride(shortcut.action, keys);
    setDrafts((current) => ({
      ...current,
      [shortcut.action]: normalizeBinding(keys),
    }));
  };

  return (
    <section className="a11y-section" aria-labelledby="a11y-shortcuts-title">
      <h3 id="a11y-shortcuts-title">Keyboard shortcuts</h3>
      <div className="a11y-inline-controls">
        <label className="a11y-field">
          <span>Filter</span>
          <input
            type="search"
            value={query}
            placeholder="Search actions"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="a11y-field">
          <span>Display</span>
          <select
            value={platform}
            onChange={(event) => setPlatform(event.target.value as Platform)}
          >
            {(Object.keys(PLATFORM_LABEL) as Platform[]).map((option) => (
              <option key={option} value={option}>
                {PLATFORM_LABEL[option]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {filtered.length === 0 ? (
        <p className="a11y-empty">No shortcuts match this filter.</p>
      ) : (
        Object.entries(groups).map(([group, items]) => (
          <div key={group} className="a11y-shortcut-group">
            <h4>{group}</h4>
            <ul className="a11y-shortcut-list">
              {items.map((shortcut) => (
                <li key={`${shortcut.scope}-${shortcut.action}`}>
                  <span className="a11y-shortcut-label">
                    {shortcut.label}
                    {shortcut.enabled ? "" : " (disabled)"}
                  </span>
                  <code>{formatBinding(shortcut.keys, platform)}</code>
                  <input
                    aria-label={`Change ${shortcut.label} binding`}
                    value={draftFor(shortcut)}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [shortcut.action]: event.target.value,
                      }))
                    }
                  />
                  <button
                    type="button"
                    className="a11y-button"
                    disabled={
                      bindingId(draftFor(shortcut)) === bindingId(shortcut.keys)
                    }
                    onClick={() => apply(shortcut)}
                  >
                    Apply
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
