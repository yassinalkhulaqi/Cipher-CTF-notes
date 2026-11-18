import { useCallback, useMemo, useRef, useState } from "react";
import { copyDocument, emptyDocument } from "./blocks";
import { BlockEditorEngine } from "./engine";
import { selectionPoint, selectionRange } from "./selection";
import {
  type Block,
  type BlockDocument,
  type BlockPatch,
  type BlockType,
  type EditorState,
  type SelectionRange,
} from "./types";

export interface BlockEditorController {
  state: EditorState;
  document: BlockDocument;
  canUndo: boolean;
  canRedo: boolean;
  focus: (blockId: string) => void;
  setSelection: (selection: SelectionRange) => void;
  setText: (blockId: string, text: string) => void;
  insert: (type: BlockType, afterId?: string) => void;
  insertAt: (index: number, type: BlockType) => void;
  split: (blockId: string, offset: number) => void;
  merge: (blockId: string) => void;
  remove: (blockId: string) => void;
  duplicate: (blockId: string) => void;
  move: (blockId: string, offset: number) => void;
  changeType: (blockId: string, type: BlockType) => void;
  update: (blockId: string, changes: Partial<Block>) => void;
  acceptSlash: (commandId: string, blockId?: string) => void;
  setSlashQuery: (query: string | null) => void;
  setMentionQuery: (query: string | null) => void;
  closeMenus: () => void;
  format: (blockId: string, format: string) => void;
  toggleTask: (blockId: string, index: number) => void;
  addItem: (blockId: string) => void;
  removeItem: (blockId: string, index: number) => void;
  addRow: (blockId: string) => void;
  addColumn: (blockId: string) => void;
  setTitle: (title: string) => void;
  setTags: (tags: string[]) => void;
  undo: () => void;
  redo: () => void;
  replaceDocument: (document: BlockDocument) => void;
  patchSince: (document: BlockDocument) => BlockPatch;
  wordCount: () => number;
}

export function useBlockEditor(initial?: BlockDocument): BlockEditorController {
  const initialDocument = useMemo(
    () => copyDocument(initial ?? emptyDocument()),
    [initial],
  );
  const engineRef = useRef<BlockEditorEngine | null>(null);
  if (engineRef.current === null)
    engineRef.current = BlockEditorEngine.fromDocument(initialDocument);
  const [state, setState] = useState<EditorState>(
    () =>
      engineRef.current?.snapshot ?? {
        document: initialDocument,
        selection: selectionRange(
          selectionPoint(initialDocument.blocks[0]?.id ?? ""),
        ),
        focusedBlockId: initialDocument.blocks[0]?.id ?? "",
        slashQuery: null,
        mentionQuery: null,
        history: [],
        future: [],
      },
  );

  const apply = useCallback(
    (mutate: (engine: BlockEditorEngine) => void) => {
      const engine = new BlockEditorEngine(state);
      mutate(engine);
      const next = engine.snapshot;
      setState(next);
    },
    [state],
  );

  const controller = useMemo<BlockEditorController>(
    () => ({
      state,
      document: state.document,
      canUndo: state.history.length > 0,
      canRedo: state.future.length > 0,
      focus: (blockId) => apply((engine) => engine.focus(blockId)),
      setSelection: (selection) =>
        apply((engine) => engine.setSelection(selection)),
      setText: (blockId, text) =>
        apply((engine) => engine.setText(blockId, text)),
      insert: (type, afterId) =>
        apply((engine) => engine.insert(type, afterId)),
      insertAt: (index, type) =>
        apply((engine) => engine.insertAt(index, type)),
      split: (blockId, offset) =>
        apply((engine) => engine.split(blockId, offset)),
      merge: (blockId) => apply((engine) => engine.merge(blockId)),
      remove: (blockId) => apply((engine) => engine.delete(blockId)),
      duplicate: (blockId) => apply((engine) => engine.duplicate(blockId)),
      move: (blockId, offset) =>
        apply((engine) => engine.move(blockId, offset)),
      changeType: (blockId, type) =>
        apply((engine) => engine.changeType(blockId, type)),
      update: (blockId, changes) =>
        apply((engine) => engine.update(blockId, changes)),
      acceptSlash: (commandId, blockId) =>
        apply((engine) => engine.acceptSlash(commandId, blockId)),
      setSlashQuery: (query) => apply((engine) => engine.setSlashQuery(query)),
      setMentionQuery: (query) =>
        apply((engine) => engine.setMentionQuery(query)),
      closeMenus: () => apply((engine) => engine.closeMenus()),
      format: (blockId, format) =>
        apply((engine) => engine.applyFormat(blockId, format)),
      toggleTask: (blockId, index) =>
        apply((engine) => engine.toggleTask(blockId, index)),
      addItem: (blockId) => apply((engine) => engine.addItem(blockId)),
      removeItem: (blockId, index) =>
        apply((engine) => engine.removeItem(blockId, index)),
      addRow: (blockId) => apply((engine) => engine.addRow(blockId)),
      addColumn: (blockId) => apply((engine) => engine.addColumn(blockId)),
      setTitle: (title) => apply((engine) => engine.setTitle(title)),
      setTags: (tags) => apply((engine) => engine.setTags(tags)),
      undo: () => apply((engine) => engine.undo()),
      redo: () => apply((engine) => engine.redo()),
      replaceDocument: (document) =>
        apply((engine) => engine.replaceDocument(document)),
      patchSince: (document) =>
        new BlockEditorEngine(state).patchSince(document),
      wordCount: () => new BlockEditorEngine(state).wordCount(),
    }),
    [apply, state],
  );

  return controller;
}
