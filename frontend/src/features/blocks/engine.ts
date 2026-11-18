import {
  addListItem,
  addTableColumn,
  addTableRow,
  blockIndex,
  changeBlockType,
  cloneBlock,
  copyDocument,
  createBlock,
  documentWordCount,
  duplicateBlock,
  insertAfter,
  moveBlockBy,
  removeBlock,
  removeListItem,
  updateBlock,
  updateBlockText,
} from "./blocks";
import { diffDocuments, mergeEntries, patchFromDiff } from "./diff";
import { normalizeDocument } from "./normalize";
import {
  caretAfterText,
  caretBeforeText,
  selectionPoint,
  selectionRange,
} from "./selection";
import { slashCommandById } from "./slashCommands";
import {
  type Block,
  type BlockDocument,
  type BlockPatch,
  type BlockType,
  type EditorState,
  type SelectionRange,
} from "./types";

const HISTORY_LIMIT = 100;

export class BlockEditorEngine {
  private state: EditorState;

  constructor(state: EditorState) {
    this.state = state;
  }

  static fromDocument(document: BlockDocument): BlockEditorEngine {
    const normalized = normalizeDocument(document);
    const first = normalized.blocks[0];
    return new BlockEditorEngine({
      document: normalized,
      selection: selectionRange(selectionPoint(first?.id ?? "")),
      focusedBlockId: first?.id ?? "",
      slashQuery: null,
      mentionQuery: null,
      history: [],
      future: [],
    });
  }

  get snapshot(): EditorState {
    return {
      ...this.state,
      document: copyDocument(this.state.document),
      selection: {
        anchor: { ...this.state.selection.anchor },
        focus: { ...this.state.selection.focus },
      },
      history: [...this.state.history],
      future: [...this.state.future],
    };
  }

  get document(): BlockDocument {
    return copyDocument(this.state.document);
  }

  get focusedBlockId(): string {
    return this.state.focusedBlockId;
  }

  get canUndo(): boolean {
    return this.state.history.length > 0;
  }

  get canRedo(): boolean {
    return this.state.future.length > 0;
  }

  setSelection(selection: SelectionRange): BlockEditorEngine {
    this.state = { ...this.state, selection };
    return this;
  }

  focus(blockId: string): BlockEditorEngine {
    this.state = { ...this.state, focusedBlockId: blockId };
    return this;
  }

  setSlashQuery(query: string | null): BlockEditorEngine {
    this.state = { ...this.state, slashQuery: query, mentionQuery: null };
    return this;
  }

  setMentionQuery(query: string | null): BlockEditorEngine {
    this.state = { ...this.state, mentionQuery: query, slashQuery: null };
    return this;
  }

  closeMenus(): BlockEditorEngine {
    this.state = { ...this.state, slashQuery: null, mentionQuery: null };
    return this;
  }

  insert(
    type: BlockType,
    afterId = this.state.focusedBlockId,
  ): BlockEditorEngine {
    const block = createBlock(type);
    const next = insertAfter(this.state.document, afterId, block);
    return this.commit(next, caretBeforeText(next, block.id));
  }

  insertAt(index: number, type: BlockType): BlockEditorEngine {
    const block = createBlock(type);
    const blocks = [...this.state.document.blocks];
    blocks.splice(Math.max(0, Math.min(index, blocks.length)), 0, block);
    const next = { ...this.state.document, blocks };
    return this.commit(next, caretBeforeText(next, block.id));
  }

  setText(blockId: string, text: string): BlockEditorEngine {
    const next = updateBlockText(this.state.document, blockId, text);
    return this.commit(next, caretAfterText(next, blockId));
  }

  update(blockId: string, changes: Partial<Block>): BlockEditorEngine {
    const next = updateBlock(this.state.document, blockId, changes);
    return this.commit(next);
  }

  split(blockId: string, offset: number): BlockEditorEngine {
    const document = this.state.document;
    const block = document.blocks.find((item) => item.id === blockId);
    if (!block) return this;
    const before = block.text.slice(0, offset);
    const after = block.text.slice(offset);
    const fresh = createBlock("paragraph", { text: after });
    const withBefore = updateBlockText(document, blockId, before);
    const next = insertAfter(withBefore, blockId, fresh);
    return this.commit(next, caretBeforeText(next, fresh.id));
  }

  merge(blockId: string): BlockEditorEngine | null {
    const document = this.state.document;
    const index = blockIndex(document, blockId);
    if (index <= 0) return null;
    const previous = document.blocks[index - 1];
    const current = document.blocks[index];
    const combined = updateBlockText(
      document,
      previous.id,
      previous.text + current.text,
    );
    const next = removeBlock(combined, current.id);
    return this.commit(next, caretAfterText(next, previous.id));
  }

  delete(blockId: string): BlockEditorEngine {
    const document = this.state.document;
    const index = blockIndex(document, blockId);
    const next = removeBlock(document, blockId);
    const fallback =
      next.blocks[Math.max(0, Math.min(index, next.blocks.length - 1))];
    return this.commit(
      next,
      fallback ? caretAfterText(next, fallback.id) : this.state.selection,
    );
  }

  duplicate(blockId: string): BlockEditorEngine {
    const next = duplicateBlock(this.state.document, blockId);
    return this.commit(next);
  }

  move(blockId: string, offset: number): BlockEditorEngine {
    const next = moveBlockBy(this.state.document, blockId, offset);
    return this.commit(next);
  }

  changeType(blockId: string, type: BlockType): BlockEditorEngine {
    const next = changeBlockType(this.state.document, blockId, type);
    return this.commit(next);
  }

  acceptSlash(
    commandId: string,
    blockId = this.state.focusedBlockId,
  ): BlockEditorEngine {
    const command = slashCommandById(commandId);
    if (!command) return this.closeMenus();
    let next = changeBlockType(this.state.document, blockId, command.blockType);
    const block = next.blocks.find((item) => item.id === blockId);
    if (block?.text.startsWith("/")) {
      next = updateBlockText(
        next,
        blockId,
        block.text.replace(/^\/[^\s]*\s*/, ""),
      );
    }
    return this.commit(next, caretAfterText(next, blockId)).closeMenus();
  }

  toggleTask(blockId: string, index: number): BlockEditorEngine {
    const block = this.state.document.blocks.find(
      (item) => item.id === blockId,
    );
    if (!block || block.type !== "list") return this;
    const checked = [...block.checked];
    checked[index] = !checked[index];
    return this.update(blockId, { checked });
  }

  addItem(blockId: string): BlockEditorEngine {
    const block = this.state.document.blocks.find(
      (item) => item.id === blockId,
    );
    if (!block || block.type !== "list") return this;
    return this.update(blockId, addListItem(block));
  }

  removeItem(blockId: string, index: number): BlockEditorEngine {
    const block = this.state.document.blocks.find(
      (item) => item.id === blockId,
    );
    if (!block || block.type !== "list") return this;
    return this.update(blockId, removeListItem(block, index));
  }

  addRow(blockId: string): BlockEditorEngine {
    const block = this.state.document.blocks.find(
      (item) => item.id === blockId,
    );
    if (!block || block.type !== "table") return this;
    return this.update(blockId, addTableRow(block));
  }

  addColumn(blockId: string): BlockEditorEngine {
    const block = this.state.document.blocks.find(
      (item) => item.id === blockId,
    );
    if (!block || block.type !== "table") return this;
    return this.update(blockId, addTableColumn(block));
  }

  applyFormat(blockId: string, format: string): BlockEditorEngine {
    const block = this.state.document.blocks.find(
      (item) => item.id === blockId,
    );
    if (!block) return this;
    if (format === "bold")
      return this.update(blockId, { text: `**${block.text}**` });
    if (format === "italic")
      return this.update(blockId, { text: `_${block.text}_` });
    if (format === "code")
      return this.update(blockId, { text: `\`${block.text}\`` });
    if (format === "link")
      return this.update(blockId, { text: `[${block.text}](url)` });
    if (format === "mention")
      return this.update(blockId, { text: `${block.text}@` });
    return this;
  }

  setTitle(title: string): BlockEditorEngine {
    return this.commit({ ...this.state.document, title });
  }

  setTags(tags: string[]): BlockEditorEngine {
    return this.commit({ ...this.state.document, tags });
  }

  setMetadata(key: string, value: string): BlockEditorEngine {
    const metadata = { ...this.state.document.metadata, [key]: value };
    return this.commit({ ...this.state.document, metadata });
  }

  replaceDocument(document: BlockDocument): BlockEditorEngine {
    return this.commit(normalizeDocument(document));
  }

  applyRemoteDocument(document: BlockDocument): BlockEditorEngine {
    const next = normalizeDocument(document);
    this.state = {
      ...this.state,
      document: next,
      selection: selectionRange(selectionPoint(next.blocks[0]?.id ?? "", 0)),
    };
    return this;
  }

  patchSince(document: BlockDocument): BlockPatch {
    const patch = patchFromDiff(document, this.state.document);
    return { ...patch, entries: mergeEntries(patch.entries) };
  }

  diffSince(document: BlockDocument) {
    return diffDocuments(document, this.state.document);
  }

  wordCount(): number {
    return documentWordCount(this.state.document);
  }

  undo(): BlockEditorEngine {
    const previous = this.state.history.at(-1);
    if (!previous) return this;
    this.state = {
      ...this.state,
      document: previous,
      history: this.state.history.slice(0, -1),
      future: [this.state.document, ...this.state.future].slice(
        0,
        HISTORY_LIMIT,
      ),
      slashQuery: null,
      mentionQuery: null,
    };
    return this;
  }

  redo(): BlockEditorEngine {
    const [next, ...remaining] = this.state.future;
    if (!next) return this;
    this.state = {
      ...this.state,
      document: next,
      history: [...this.state.history, this.state.document].slice(
        -HISTORY_LIMIT,
      ),
      future: remaining,
      slashQuery: null,
      mentionQuery: null,
    };
    return this;
  }

  private commit(
    document: BlockDocument,
    selection?: SelectionRange,
  ): BlockEditorEngine {
    this.state = {
      ...this.state,
      document: normalizeDocument(document),
      selection: selection ?? this.state.selection,
      history: [...this.state.history, this.state.document].slice(
        -HISTORY_LIMIT,
      ),
      future: [],
    };
    return this;
  }
}

export function blockAt(
  document: BlockDocument,
  blockId: string,
): Block | null {
  return document.blocks.find((block) => block.id === blockId) ?? null;
}

export function detachedBlock(
  document: BlockDocument,
  blockId: string,
): Block | null {
  const block = blockAt(document, blockId);
  return block ? cloneBlock(block) : null;
}
