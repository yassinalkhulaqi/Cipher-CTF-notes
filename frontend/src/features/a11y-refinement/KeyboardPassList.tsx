/** Keyboard pass list with full keyboard activation and group filtering. */

import { useState } from "react";

import { V3Panel } from "../../v3/components/V3Panel";
import {
  bindingsForGroup,
  groupLabel,
  keyboardPass,
  summarizeMap,
} from "./keyboard";
import type { KeyboardBindingView, KeyboardMapView } from "./types";

export interface KeyboardPassListProps {
  map: KeyboardMapView;
  locale?: string;
  onSelect?: (binding: KeyboardBindingView) => void;
}

export function KeyboardPassList({
  map,
  locale = "en",
  onSelect,
}: KeyboardPassListProps) {
  const [group, setGroup] = useState("navigation");
  const groups = Object.keys(map.groups).sort();
  const pass = keyboardPass(map);
  const summary = summarizeMap(map);
  const active = group in map.groups ? group : (groups[0] ?? "navigation");
  const bindings = bindingsForGroup(map, active);

  return (
    <V3Panel
      title="Keyboard pass"
      subtitle={`${summary.bindings} bindings · ${summary.conflicts} conflicts`}
      density="compact"
      actions={
        <span className="a11y-refine__badge" data-complete={pass.complete}>
          {pass.complete ? "complete" : "needs work"}
        </span>
      }
    >
      <div
        className="a11y-refine__groups"
        role="tablist"
        aria-label="Keyboard binding groups"
      >
        {groups.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={name === active}
            data-active={name === active}
            className="a11y-refine__group-tab"
            onClick={() => setGroup(name)}
          >
            {groupLabel(name)}
            <span className="a11y-refine__sr-only">
              {" "}
              ({map.groups[name].length} shortcuts)
            </span>
          </button>
        ))}
      </div>
      <ul
        className="a11y-refine__bindings"
        data-group={active}
        aria-label={groupLabel(active)}
      >
        {bindings.map((binding) => (
          <li
            key={binding.action}
            data-action={binding.action}
            data-enabled={binding.enabled}
          >
            <button
              type="button"
              className="a11y-refine__binding"
              aria-label={`${binding.label}, ${binding.display}`}
              onClick={() => onSelect?.(binding)}
              disabled={!binding.enabled}
            >
              <span className="a11y-refine__binding-label">
                {binding.label}
              </span>
              <kbd className="a11y-refine__kbd" aria-hidden="true">
                {binding.display}
              </kbd>
              <span className="a11y-refine__sr-only">
                {locale} keyboard binding
              </span>
            </button>
          </li>
        ))}
      </ul>
    </V3Panel>
  );
}
