/** Global Ctrl+K command bar with grouped results and focus restore. */

import { useEffect, useRef } from "react";
import type { Dispatch, KeyboardEvent } from "react";

import { BreadcrumbTrail } from "./BreadcrumbTrail";
import "./commands.css";
import { renderCommand } from "./parse";
import { groupHits, rankCommands } from "./scoring";
import { flattenGroups, isCommandBarShortcut } from "./state";
import type { PaletteAction, PaletteState } from "./state";
import type {
  CommandContext,
  CommandInvocation,
  CommandSpec,
  NavNode,
} from "./types";
import { ArgumentForm } from "./ArgumentForm";

export interface CommandPaletteV3Props {
  state: PaletteState;
  dispatch: Dispatch<PaletteAction>;
  context: CommandContext;
  crumbs?: NavNode[];
  commands?: CommandSpec[];
  usageScore?: (id: string) => number;
  onExecute?: (invocation: CommandInvocation) => void;
}

export function invocationFor(
  command: CommandSpec,
  values: Record<string, string>,
): CommandInvocation {
  return {
    command_id: command.id,
    arguments: { ...values },
    source: "palette",
    context_ref: "",
  };
}

export function useCommandBarHotkey(
  isOpen: boolean,
  onOpen: () => void,
  onClose: () => void,
): void {
  useEffect(() => {
    const listener = (event: globalThis.KeyboardEvent) => {
      if (isCommandBarShortcut(event)) {
        event.preventDefault();
        onOpen();
        return;
      }
      if (event.key === "Escape" && isOpen) {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [isOpen, onOpen, onClose]);
}

export function CommandPaletteV3({
  state,
  dispatch,
  context,
  crumbs = [],
  commands = [],
  usageScore,
  onExecute,
}: CommandPaletteV3Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hits = flattenGroups(state.groups);

  useEffect(() => {
    if (state.open) inputRef.current?.focus();
  }, [state.open]);

  useEffect(() => {
    if (!state.open && state.restoreFocus) {
      document.getElementById(state.restoreFocus)?.focus();
    }
  }, [state.open, state.restoreFocus]);

  const run = (invocation: CommandInvocation) => {
    onExecute?.(invocation);
    dispatch({ type: "submit" });
  };

  const selectCurrent = () => {
    const hit = hits[state.selected];
    if (!hit) return;
    if (hit.command.arguments.some((argument) => argument.required)) {
      dispatch({ type: "edit-arguments", command: hit.command });
      return;
    }
    run(invocationFor(hit.command, {}));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "Tab") {
      event.preventDefault();
      dispatch({ type: "move", delta: 1 });
    } else if (
      event.key === "ArrowUp" ||
      (event.key === "Tab" && event.shiftKey)
    ) {
      event.preventDefault();
      dispatch({ type: "move", delta: -1 });
    } else if (event.key === "Enter") {
      event.preventDefault();
      selectCurrent();
    } else if (event.key === "Escape") {
      event.preventDefault();
      dispatch({ type: "close" });
    }
  };

  if (!state.open) return null;

  return (
    <div
      className="v3c-palette"
      data-testid="command-palette"
      data-density="compact"
      role="dialog"
      aria-label="Command bar"
      aria-modal="true"
    >
      <div className="v3c-palette__toolbar">
        <span className="v3c-palette__prompt" aria-hidden="true">
          ›
        </span>
        <input
          ref={inputRef}
          data-testid="command-input"
          className="v3c-palette__input"
          type="text"
          aria-label="Search commands"
          value={state.query}
          placeholder="Type a command or search actions…"
          onChange={(event) => {
            const value = event.target.value;
            const groups = commands.length
              ? groupHits(
                  rankCommands(value, commands, context, { usage: usageScore }),
                )
              : state.groups;
            dispatch({ type: "query", value, groups });
          }}
          onKeyDown={handleKeyDown}
        />
        <kbd className="v3c-palette__kbd">Esc</kbd>
      </div>
      <div className="v3c-palette__meta" data-testid="palette-context">
        <span>{context.pane_id}</span>
        {context.entity && <span>{context.entity.ref}</span>}
        {context.focus_active && <span>Focus mode</span>}
        <BreadcrumbTrail crumbs={crumbs} compact />
      </div>
      {state.pending ? (
        <ArgumentForm
          command={state.pending}
          values={state.draft}
          onChange={(name, value) =>
            dispatch({ type: "set-argument", name, value })
          }
          onSubmit={(values) =>
            state.pending && run(invocationFor(state.pending, values))
          }
          onCancel={() => dispatch({ type: "cancel-arguments" })}
        />
      ) : (
        <div className="v3c-palette__results" data-testid="command-results">
          {!hits.length && (
            <p className="v3c-palette__empty">No matching commands</p>
          )}
          {state.groups.map((group) => {
            const collapsed = state.collapsed.includes(group.group);
            return (
              <section
                className="v3c-palette__group"
                data-group={group.group}
                key={group.group}
              >
                <button
                  type="button"
                  className="v3c-palette__group-title"
                  aria-expanded={!collapsed}
                  onClick={() =>
                    dispatch({ type: "toggle-group", group: group.group })
                  }
                >
                  {group.label}
                  <span>{group.hits.length}</span>
                </button>
                {!collapsed &&
                  group.hits.map((hit) => {
                    const index = hits.indexOf(hit);
                    return (
                      <button
                        type="button"
                        key={hit.command.id}
                        className="v3c-palette__item"
                        data-testid={`command-${hit.command.id}`}
                        data-selected={index === state.selected}
                        aria-current={index === state.selected}
                        onMouseEnter={() => dispatch({ type: "jump", index })}
                        onClick={() => {
                          dispatch({ type: "jump", index });
                          selectCurrent();
                        }}
                      >
                        <span className="v3c-palette__item-title">
                          {hit.command.title}
                        </span>
                        <span className="v3c-palette__item-id">
                          {renderCommand(
                            invocationFor(hit.command, {}),
                            hit.command,
                          )}
                        </span>
                        <span className="v3c-palette__item-score">
                          {hit.score.toFixed(1)}
                        </span>
                      </button>
                    );
                  })}
              </section>
            );
          })}
        </div>
      )}
      <footer className="v3c-palette__footer">
        <span>↑↓ navigate</span>
        <span>↵ run</span>
        <span>Tab next</span>
        <span>Esc close</span>
      </footer>
    </div>
  );
}
