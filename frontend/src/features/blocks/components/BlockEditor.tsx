import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { blockPlainText } from "../blocks";
import {
  resolveKeyboardAction,
  slashQueryForValue,
  mentionQueryForValue,
} from "../keyboard";
import { buildMentionIndex } from "../mentions";
import { filterSlashCommands } from "../slashCommands";
import {
  type Block,
  type BlockDocument,
  type CalloutTone,
  type MentionSuggestion,
  type SlashCommand,
} from "../types";
import { useBlockEditor } from "../useBlockEditor";
import { BlockToolbar, type ToolbarAction } from "./BlockToolbar";
import { BlockView } from "./BlockView";
import { MentionMenu } from "./MentionMenu";
import { SlashMenu } from "./SlashMenu";

export interface BlockEditorProps {
  initialDocument?: BlockDocument;
  readOnly?: boolean;
  ariaLabel?: string;
  onDocumentChange?: (document: BlockDocument) => void;
  onSave?: (document: BlockDocument) => void;
}

export function BlockEditor({
  initialDocument,
  readOnly = false,
  ariaLabel = "Block editor",
  onDocumentChange,
  onSave,
}: BlockEditorProps) {
  const editor = useBlockEditor(initialDocument);
  const [slashIndex, setSlashIndex] = useState(0);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [saving, setSaving] = useState(false);
  const changeHandler = useRef(onDocumentChange);
  changeHandler.current = onDocumentChange;
  const saveHandler = useRef(onSave);
  saveHandler.current = onSave;

  const document = editor.document;
  const commands = useMemo(
    () =>
      editor.state.slashQuery === null
        ? []
        : filterSlashCommands(editor.state.slashQuery),
    [editor.state.slashQuery],
  );
  const suggestions = useMemo(() => {
    if (editor.state.mentionQuery === null) return [];
    const index = buildMentionIndex(document.blocks);
    return index.suggestions(editor.state.mentionQuery, undefined, 8);
  }, [document.blocks, editor.state.mentionQuery]);

  const activeBlock =
    document.blocks.find((block) => block.id === editor.state.focusedBlockId) ??
    null;

  const notifyChange = (next: BlockDocument) => {
    changeHandler.current?.(next);
  };

  const updateText = (block: Block, text: string) => {
    editor.setText(block.id, text);
    notifyChange({
      ...document,
      blocks: document.blocks.map((item) =>
        item.id === block.id ? { ...item, text } : item,
      ),
    });
    const caret = text.length;
    const slash = slashQueryForValue(text, caret);
    const mention = mentionQueryForValue(text, caret);
    if (slash !== null) {
      editor.setSlashQuery(slash);
      setSlashIndex(0);
    } else if (mention !== null) {
      editor.setMentionQuery(mention);
      setMentionIndex(0);
    } else {
      editor.closeMenus();
    }
  };

  const chooseCommand = (
    command: SlashCommand,
    blockId = editor.state.focusedBlockId,
  ) => {
    editor.acceptSlash(command.id, blockId);
    const next = {
      ...document,
      blocks: document.blocks.map((block) =>
        block.id === blockId ? { ...block, type: command.blockType } : block,
      ),
    };
    notifyChange(next);
  };

  const chooseSuggestion = (
    suggestion: MentionSuggestion,
    blockId = editor.state.focusedBlockId,
  ) => {
    const block = document.blocks.find((item) => item.id === blockId);
    if (!block) return;
    const token = `@[${suggestion.label}](${suggestion.kind}:${suggestion.target})`;
    const text = block.text.replace(/@[^\s@]*$/, token);
    editor.setText(blockId, text);
    editor.closeMenus();
    notifyChange({
      ...document,
      blocks: document.blocks.map((item) =>
        item.id === blockId ? { ...item, text } : item,
      ),
    });
  };

  const handleKeyDown = (
    block: Block,
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) => {
    const target = event.currentTarget;
    const resolved = resolveKeyboardAction({
      key: event.key,
      ctrlKey: event.ctrlKey,
      metaKey: event.metaKey,
      shiftKey: event.shiftKey,
      altKey: event.altKey,
      selectionStart: target.selectionStart,
      selectionEnd: target.selectionEnd,
      value: target.value,
      slashOpen: editor.state.slashQuery !== null,
      mentionOpen: editor.state.mentionQuery !== null,
      menuCount: Math.max(commands.length, suggestions.length),
      activeIndex: Math.max(slashIndex, mentionIndex),
    });
    if (resolved.kind === "none") return;
    event.preventDefault();
    if (editor.state.mentionQuery !== null) {
      if (resolved.kind === "move-down") {
        setMentionIndex(
          (current) => (current + 1) % Math.max(1, suggestions.length),
        );
        return;
      }
      if (resolved.kind === "move-up") {
        setMentionIndex(
          (current) =>
            (current - 1 + Math.max(1, suggestions.length)) %
            Math.max(1, suggestions.length),
        );
        return;
      }
      if (resolved.kind === "accept-mention") {
        const suggestion = suggestions[mentionIndex] ?? suggestions[0];
        if (suggestion) chooseSuggestion(suggestion, block.id);
        return;
      }
    }
    if (editor.state.slashQuery !== null) {
      if (resolved.kind === "move-down") {
        setSlashIndex(
          (current) => (current + 1) % Math.max(1, commands.length),
        );
        return;
      }
      if (resolved.kind === "move-up") {
        setSlashIndex(
          (current) =>
            (current - 1 + Math.max(1, commands.length)) %
            Math.max(1, commands.length),
        );
        return;
      }
      if (resolved.kind === "accept-slash") {
        const command = commands[slashIndex] ?? commands[0];
        if (command) chooseCommand(command, block.id);
        return;
      }
    }
    if (resolved.kind === "split") {
      editor.split(block.id, target.selectionStart);
    } else if (resolved.kind === "merge") {
      editor.merge(block.id);
    } else if (resolved.kind === "delete-block") {
      editor.remove(block.id);
    } else if (resolved.kind === "move-up") {
      editor.move(block.id, -1);
    } else if (resolved.kind === "move-down") {
      editor.move(block.id, 1);
    } else if (resolved.kind === "undo") {
      editor.undo();
    } else if (resolved.kind === "redo") {
      editor.redo();
    } else if (resolved.kind === "duplicate") {
      editor.duplicate(block.id);
    } else if (resolved.kind === "indent" || resolved.kind === "outdent") {
      editor.update(block.id, {
        level: Math.max(
          1,
          Math.min(6, block.level + (resolved.kind === "indent" ? 1 : -1)),
        ),
      });
    } else if (resolved.kind === "open-slash") {
      editor.setSlashQuery("");
      setSlashIndex(0);
    } else if (resolved.kind === "format" && resolved.payload === "mention") {
      editor.setMentionQuery("");
      setMentionIndex(0);
    } else if (resolved.kind === "format" && resolved.payload) {
      editor.format(block.id, resolved.payload);
    }
    notifyChange(editor.document);
  };

  const handleAction = (action: ToolbarAction) => {
    if (readOnly) return;
    if (action.id === "undo") editor.undo();
    else if (action.id === "redo") editor.redo();
    else if (action.id === "bold" || action.id === "italic")
      editor.format(editor.state.focusedBlockId, action.id);
    else if (action.id === "duplicate")
      editor.duplicate(editor.state.focusedBlockId);
    else if (action.id === "save") {
      setSaving(true);
      saveHandler.current?.(document);
      window.setTimeout(() => setSaving(false), 300);
    } else if (action.blockType) {
      editor.changeType(editor.state.focusedBlockId, action.blockType);
    }
    notifyChange(editor.document);
  };

  return (
    <div className="block-editor" aria-label={ariaLabel}>
      {!readOnly ? (
        <BlockToolbar
          activeType={activeBlock?.type}
          canUndo={editor.canUndo}
          canRedo={editor.canRedo}
          saving={saving}
          onAction={handleAction}
        />
      ) : null}
      <div className="block-editor__surface">
        {document.blocks.map((block) => (
          <div className="block-editor__row" key={block.id}>
            <BlockView
              block={block}
              readOnly={readOnly}
              selected={editor.state.focusedBlockId === block.id}
              onChangeText={(text) => updateText(block, text)}
              onFocus={() => editor.focus(block.id)}
              onKeyDown={(event) => handleKeyDown(block, event)}
              onToggleTask={(index) => {
                editor.toggleTask(block.id, index);
                notifyChange(editor.document);
              }}
              onItemChange={(index, text) => {
                const items = [...block.items];
                items[index] = text;
                editor.update(block.id, { items });
                notifyChange(editor.document);
              }}
              onAddItem={() => {
                editor.addItem(block.id);
                notifyChange(editor.document);
              }}
              onCellChange={(rowIndex, columnIndex, text) => {
                const rows = block.rows.map((row) => [...row]);
                rows[rowIndex] = rows[rowIndex] ?? [];
                rows[rowIndex][columnIndex] = text;
                editor.update(block.id, { rows });
                notifyChange(editor.document);
              }}
              onAddRow={() => {
                editor.addRow(block.id);
                notifyChange(editor.document);
              }}
              onToneChange={(tone: CalloutTone) => {
                editor.update(block.id, { tone });
                notifyChange(editor.document);
              }}
            />
            {editor.state.focusedBlockId === block.id &&
            editor.state.slashQuery !== null ? (
              <SlashMenu
                query={editor.state.slashQuery}
                activeIndex={slashIndex}
                onHover={setSlashIndex}
                onSelect={(command) => chooseCommand(command, block.id)}
              />
            ) : null}
            {editor.state.focusedBlockId === block.id &&
            editor.state.mentionQuery !== null ? (
              <MentionMenu
                suggestions={suggestions}
                activeIndex={mentionIndex}
                onHover={setMentionIndex}
                onSelect={(suggestion) =>
                  chooseSuggestion(suggestion, block.id)
                }
              />
            ) : null}
          </div>
        ))}
      </div>
      <footer className="block-editor__footer">
        {document.blocks.length} blocks · {editor.wordCount()} words · revision{" "}
        {document.revision}
      </footer>
    </div>
  );
}

export function editorText(document: BlockDocument): string {
  return document.blocks.map(blockPlainText).join("\n\n");
}
