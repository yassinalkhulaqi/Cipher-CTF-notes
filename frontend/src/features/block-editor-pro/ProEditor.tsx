/** Professional block editor surface with slash commands and a diff gutter. */

import { useCallback, useMemo, useReducer, useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";

import "./block-editor-pro.css";

import {
  BLOCK_LABELS,
  INLINE_MARKS,
  SLASH_BLOCK_KINDS,
  applyInlineMark,
  blockLabel,
  checksum,
  countWords,
  createBlock,
  createInitialState,
  diffDeltas,
  editorReducer,
  findMatches,
} from "./state";
import type {
  BlockKind,
  InlineMark,
  ProBlock,
  ProDocument,
  SnapshotMeta,
} from "./state";

export interface ProEditorProps {
  document: ProDocument;
  revision?: number;
  snapshots?: SnapshotMeta[];
  loading?: boolean;
  onSave?: (document: ProDocument) => Promise<number | void>;
  onSnapshot?: (reason: string) => Promise<void>;
  onRestore?: (snapshotId: string) => Promise<void>;
}

const MARK_GLYPHS: Record<InlineMark, string> = {
  bold: "B",
  italic: "I",
  code: "</>",
  link: "↗",
};

export function ProEditor({
  document,
  revision = 0,
  snapshots = [],
  loading = false,
  onSave,
  onSnapshot,
  onRestore,
}: ProEditorProps) {
  const [state, dispatch] = useReducer(editorReducer, undefined, () =>
    createInitialState(document, revision),
  );
  const [selection, setSelection] = useState("");
  const [slashQuery, setSlashQuery] = useState("");
  const [snapshotReason, setSnapshotReason] = useState("manual");
  const sequence = useRef(0);

  const selected = useMemo(
    () =>
      state.document.blocks.find((block) => block.id === state.selectedId) ??
      null,
    [state.document.blocks, state.selectedId],
  );
  const matches = useMemo(
    () => findMatches(state.document, state.find),
    [state.document, state.find],
  );
  const words = useMemo(() => countWords(state.document), [state.document]);
  const liveChecksum = useMemo(
    () => checksum(state.document),
    [state.document],
  );
  const deltas = useMemo(
    () => diffDeltas(document, state.document),
    [document, state.document],
  );

  const nextId = useCallback(() => {
    sequence.current += 1;
    return `local-${sequence.current}`;
  }, []);

  const insert = useCallback(
    (kind: BlockKind, text = "") => {
      dispatch({ type: "insert", block: createBlock(nextId(), kind, text) });
      setSlashQuery("");
    },
    [nextId],
  );

  const applyMark = useCallback(
    (mark: InlineMark) => {
      if (!selected || !selection.trim()) return;
      dispatch({
        type: "update-block",
        id: selected.id,
        patch: applyInlineMark(
          selected,
          mark,
          selection,
          "https://example.test",
        ),
      });
      setSelection("");
    },
    [selected, selection],
  );

  const save = useCallback(async () => {
    if (!onSave) {
      dispatch({ type: "saved", revision: state.revision });
      return;
    }
    dispatch({ type: "saving" });
    try {
      const result = await onSave(state.document);
      dispatch({
        type: "saved",
        revision: typeof result === "number" ? result : state.revision + 1,
      });
    } catch (error) {
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "save failed",
      });
    }
  }, [onSave, state.document, state.revision]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>, block: ProBlock) => {
      if (event.key === "/" && block.text === "") {
        dispatch({ type: "set-slash", open: true });
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
      }
    },
    [save],
  );

  const updateTitle = (event: ChangeEvent<HTMLInputElement>) => {
    dispatch({ type: "set-title", title: event.target.value });
  };

  const filteredCommands = SLASH_BLOCK_KINDS.filter((kind) =>
    `${kind} ${BLOCK_LABELS[kind]}`
      .toLowerCase()
      .includes(slashQuery.toLowerCase()),
  );

  if (loading) {
    return (
      <section className="bep-editor bep-editor--loading" aria-busy="true">
        <div className="bep-editor__skeleton" />
      </section>
    );
  }

  return (
    <section className="bep-editor" data-focus={state.focusMode}>
      <header className="bep-editor__header">
        <div className="bep-editor__heading">
          <input
            className="bep-editor__title"
            aria-label="Document title"
            value={state.document.title}
            onChange={updateTitle}
          />
          <span className="bep-editor__meta">
            r{state.revision} · {state.document.blocks.length} blocks · {words}{" "}
            words
          </span>
        </div>
        <div className="bep-editor__actions">
          <span className="bep-editor__checksum" title="Content checksum">
            {liveChecksum}
          </span>
          <button
            type="button"
            className="bep-editor__button"
            data-active={state.focusMode}
            onClick={() => dispatch({ type: "toggle-focus" })}
          >
            {state.focusMode ? "Exit focus" : "Focus mode"}
          </button>
          <button
            type="button"
            className="bep-editor__button"
            data-active={state.diffOpen}
            onClick={() =>
              dispatch({ type: "set-diff", open: !state.diffOpen })
            }
          >
            Diff gutter
          </button>
          <button
            type="button"
            className="bep-editor__button bep-editor__button--primary"
            disabled={!state.dirty || state.status === "saving"}
            onClick={() => void save()}
          >
            {state.status === "saving" ? "Saving…" : "Save"}
          </button>
        </div>
      </header>

      <div
        className="bep-editor__toolbar"
        role="toolbar"
        aria-label="Inline formatting"
      >
        {INLINE_MARKS.map((mark) => (
          <button
            key={mark}
            type="button"
            className="bep-editor__mark"
            data-mark={mark}
            disabled={!selected}
            onClick={() => applyMark(mark)}
            title={`Apply ${mark}`}
          >
            {MARK_GLYPHS[mark]}
          </button>
        ))}
        <input
          className="bep-editor__selection"
          aria-label="Selected text"
          placeholder="selected text"
          value={selection}
          onChange={(event) => setSelection(event.target.value)}
        />
        <button
          type="button"
          className="bep-editor__button"
          onClick={() => dispatch({ type: "set-find", open: !state.findOpen })}
        >
          Find / replace
        </button>
        <button
          type="button"
          className="bep-editor__button"
          onClick={() => insert("paragraph")}
        >
          + Block
        </button>
      </div>

      {state.findOpen && (
        <div className="bep-editor__findbar" role="search">
          <input
            aria-label="Find"
            placeholder="find"
            value={state.find}
            onChange={(event) =>
              dispatch({ type: "find", value: event.target.value })
            }
          />
          <input
            aria-label="Replace"
            placeholder="replace"
            value={state.replace}
            onChange={(event) =>
              dispatch({ type: "replace", value: event.target.value })
            }
          />
          <button
            type="button"
            className="bep-editor__button"
            onClick={() => dispatch({ type: "replace-all" })}
          >
            Replace all
          </button>
          <span className="bep-editor__match-count">
            {matches.length} match(es)
          </span>
          <button
            type="button"
            className="bep-editor__button"
            onClick={() => dispatch({ type: "set-find", open: false })}
          >
            Close
          </button>
        </div>
      )}

      {state.slashOpen && (
        <div
          className="bep-editor__slash"
          role="menu"
          aria-label="Block commands"
        >
          <input
            aria-label="Filter commands"
            placeholder="Type a block kind…"
            value={slashQuery}
            onChange={(event) => setSlashQuery(event.target.value)}
          />
          <ul>
            {filteredCommands.map((kind) => (
              <li key={kind}>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => insert(kind)}
                >
                  <span className="bep-editor__slash-kind">{kind}</span>
                  <span>{BLOCK_LABELS[kind]}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bep-editor__body">
        <ol className="bep-editor__blocks">
          {state.document.blocks.map((block, index) => {
            const delta = deltas.find((item) => item.id === block.id);
            return (
              <li
                key={block.id}
                className="bep-editor__block"
                data-selected={block.id === state.selectedId}
                onClick={() => dispatch({ type: "select", id: block.id })}
              >
                <span
                  className="bep-editor__gutter"
                  data-delta={delta?.kind ?? "none"}
                >
                  {delta
                    ? delta.kind.slice(0, 1).toUpperCase()
                    : String(index + 1)}
                </span>
                <span className="bep-editor__badge">{blockLabel(block)}</span>
                {block.kind === "divider" ? (
                  <hr className="bep-editor__divider" />
                ) : (
                  <textarea
                    className="bep-editor__text"
                    aria-label={`${blockLabel(block)} text`}
                    value={block.text}
                    rows={block.kind === "code" ? 4 : 2}
                    onKeyDown={(event) => onKeyDown(event, block)}
                    onChange={(event) =>
                      dispatch({
                        type: "update-block",
                        id: block.id,
                        patch: { text: event.target.value },
                      })
                    }
                    onSelect={(event) =>
                      setSelection(
                        event.currentTarget.value.slice(
                          event.currentTarget.selectionStart,
                          event.currentTarget.selectionEnd,
                        ),
                      )
                    }
                  />
                )}
                {block.kind === "list" && (
                  <ul className="bep-editor__items">
                    {block.items.map((item, itemIndex) => (
                      <li key={`${block.id}-${itemIndex}`}>{item}</li>
                    ))}
                  </ul>
                )}
                <span className="bep-editor__block-actions">
                  <button
                    type="button"
                    aria-label="Move block up"
                    disabled={index === 0}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({
                        type: "move",
                        id: block.id,
                        target: index - 1,
                      });
                    }}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label="Move block down"
                    disabled={index === state.document.blocks.length - 1}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({
                        type: "move",
                        id: block.id,
                        target: index + 1,
                      });
                    }}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label="Delete block"
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({ type: "delete", id: block.id });
                    }}
                  >
                    ×
                  </button>
                </span>
              </li>
            );
          })}
        </ol>

        {state.diffOpen && (
          <aside className="bep-editor__diff" aria-label="Diff gutter view">
            <h3>Changes since last save</h3>
            {deltas.length === 0 ? (
              <p className="bep-editor__empty">No differences.</p>
            ) : (
              <ul>
                {deltas.map((item) => (
                  <li key={`${item.id}-${item.kind}`} data-kind={item.kind}>
                    <span>{item.kind}</span> {item.id}: {item.text || "—"}
                  </li>
                ))}
              </ul>
            )}
          </aside>
        )}
      </div>

      <footer className="bep-editor__footer">
        <div className="bep-editor__snapshots">
          <label>
            Reason
            <input
              value={snapshotReason}
              onChange={(event) => setSnapshotReason(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="bep-editor__button"
            disabled={!onSnapshot}
            onClick={() => onSnapshot?.(snapshotReason)}
          >
            Snapshot
          </button>
          {snapshots.slice(-3).map((snapshot) => (
            <button
              key={snapshot.id}
              type="button"
              className="bep-editor__snapshot"
              disabled={!onRestore}
              onClick={() => onRestore?.(snapshot.id)}
            >
              r{snapshot.revision} · {snapshot.reason}
            </button>
          ))}
        </div>
        <span className="bep-editor__status" data-status={state.status}>
          {state.error || (state.dirty ? "unsaved changes" : `${state.status}`)}
        </span>
      </footer>
    </section>
  );
}

export default ProEditor;
