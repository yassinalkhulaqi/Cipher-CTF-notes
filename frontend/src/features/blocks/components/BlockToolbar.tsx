import { memo } from "react";
import { type BlockType } from "../types";

export interface ToolbarAction {
  id: string;
  label: string;
  blockType?: BlockType;
  disabled?: boolean;
}

const ACTIONS: ToolbarAction[] = [
  { id: "undo", label: "Undo" },
  { id: "redo", label: "Redo" },
  { id: "paragraph", label: "Text", blockType: "paragraph" },
  { id: "heading", label: "Heading", blockType: "heading" },
  { id: "code", label: "Code", blockType: "code" },
  { id: "quote", label: "Quote", blockType: "quote" },
  { id: "list", label: "List", blockType: "list" },
  { id: "table", label: "Table", blockType: "table" },
  { id: "callout", label: "Callout", blockType: "callout" },
  { id: "divider", label: "Divider", blockType: "divider" },
  { id: "image", label: "Image", blockType: "image" },
  { id: "bold", label: "Bold" },
  { id: "italic", label: "Italic" },
  { id: "duplicate", label: "Duplicate" },
  { id: "save", label: "Save" },
];

export interface BlockToolbarProps {
  activeType?: BlockType;
  canUndo?: boolean;
  canRedo?: boolean;
  saving?: boolean;
  onAction: (action: ToolbarAction) => void;
}

export const BlockToolbar = memo(function BlockToolbar({
  activeType,
  canUndo = false,
  canRedo = false,
  saving = false,
  onAction,
}: BlockToolbarProps) {
  return (
    <div className="block-toolbar" role="toolbar" aria-label="Block formatting">
      {ACTIONS.map((action) => {
        const disabled =
          (action.id === "undo" && !canUndo) ||
          (action.id === "redo" && !canRedo) ||
          (action.id === "save" && saving) ||
          action.disabled === true;
        const active =
          action.blockType !== undefined && action.blockType === activeType;
        return (
          <button
            aria-label={action.label}
            aria-pressed={active}
            className={`block-toolbar__button${active ? " is-active" : ""}`}
            data-action={action.id}
            disabled={disabled}
            key={action.id}
            type="button"
            onClick={() => onAction(action)}
          >
            {action.label}
          </button>
        );
      })}
    </div>
  );
});

export function toolbarAction(id: string): ToolbarAction | null {
  return ACTIONS.find((action) => action.id === id) ?? null;
}

export function toolbarTypes(): BlockType[] {
  return ACTIONS.flatMap((action) =>
    action.blockType ? [action.blockType] : [],
  );
}
