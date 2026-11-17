import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import {
  ChevronRight,
  FileText,
  Flag,
  Folder,
  FolderOpen,
  Pin,
} from "lucide-react";
import { StatusIcon } from "../StatusIcon";
import type { FlatNode } from "../../lib/tree";
import type { TreeNode } from "../../lib/types";

export interface TreeRowProps {
  row: FlatNode;
  selected: boolean;
  focusable: boolean;
  expanded: boolean;
  dragging: boolean;
  dropTarget: boolean;
  renaming: boolean;
  onToggle: (id: number) => void;
  onSelect: (id: number) => void;
  onRename: (id: number, title: string) => Promise<void>;
  onRenameDone: () => void;
  onKeyNavigate: (event: KeyboardEvent<HTMLDivElement>, row: FlatNode) => void;
  onStartRename: (node: TreeNode) => void;
  onContext: (event: MouseEvent<HTMLDivElement>, node: TreeNode) => void;
  onDragStart: (event: DragEvent<HTMLDivElement>, node: TreeNode) => void;
  onDragEnd: () => void;
  onDragOver: (event: DragEvent<HTMLDivElement>, node: TreeNode) => void;
  onDrop: (event: DragEvent<HTMLDivElement>, node: TreeNode) => void;
}

export function TreeRow({
  row,
  selected,
  focusable,
  expanded,
  dragging,
  dropTarget,
  renaming,
  onToggle,
  onSelect,
  onRename,
  onRenameDone,
  onKeyNavigate,
  onStartRename,
  onContext,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}: TreeRowProps) {
  const { node, depth } = row;
  const folder = node.kind === "folder";
  const open = folder && expanded;
  const rowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(node.title);

  useEffect(() => {
    setTitle(node.title);
  }, [node.title]);

  useEffect(() => {
    if (!renaming) return;
    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 10);
    return () => window.clearTimeout(timer);
  }, [renaming]);

  const activate = () => {
    if (folder) onToggle(node.id);
    else onSelect(node.id);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (renaming) return;
    if (event.key === "F2") {
      event.preventDefault();
      event.stopPropagation();
      onStartRename(node);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate();
      return;
    }
    onKeyNavigate(event, row);
  };

  const commit = () => {
    const next = title.trim();
    if (!next || next === node.title) {
      onRenameDone();
      return;
    }
    void onRename(node.id, next);
  };

  return (
    <div
      ref={rowRef}
      className={`tree-row ${selected ? "selected" : ""} ${dragging ? "dragging" : ""} ${
        dropTarget ? "drop-target" : ""
      }`}
      style={{ paddingLeft: `${5 + depth * 13}px` }}
      data-node-id={node.id}
      role="treeitem"
      aria-level={depth + 1}
      aria-selected={selected}
      aria-expanded={folder ? open : undefined}
      tabIndex={focusable ? 0 : -1}
      title={renaming ? undefined : node.path || node.title}
      draggable={!renaming}
      onClick={() => {
        if (!renaming) activate();
      }}
      onKeyDown={onKeyDown}
      onContextMenu={(event) => onContext(event, node)}
      onDragStart={(event) => onDragStart(event, node)}
      onDragEnd={onDragEnd}
      onDragOver={(event) => onDragOver(event, node)}
      onDrop={(event) => onDrop(event, node)}
    >
      {folder ? (
        <button
          type="button"
          className={`chevron ${open ? "open" : ""}`}
          onClick={(event) => {
            event.stopPropagation();
            onToggle(node.id);
          }}
          tabIndex={-1}
          aria-label={open ? "Collapse folder" : "Expand folder"}
        >
          <ChevronRight />
        </button>
      ) : (
        <span className="chevron" />
      )}
      <span className={`node-icon ${folder ? "folder" : ""}`}>
        {folder ? open ? <FolderOpen /> : <Folder /> : <FileText />}
      </span>
      {renaming ? (
        <input
          ref={inputRef}
          className="tree-inline-input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onClick={(event) => event.stopPropagation()}
          onBlur={commit}
          onKeyDown={(event) => {
            event.stopPropagation();
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              setTitle(node.title);
              onRenameDone();
            }
          }}
          aria-label={`Rename ${node.title}`}
          spellCheck={false}
        />
      ) : (
        <span className={`node-title ${folder ? "folder" : ""}`}>
          {node.title}
        </span>
      )}
      {!renaming && node.pinned ? (
        <span className="row-pin" title="Pinned">
          <Pin />
        </span>
      ) : null}
      {!renaming && node.flag ? (
        <span className="row-flag" title={node.flag}>
          <Flag />
        </span>
      ) : null}
      {!renaming && !folder ? (
        <StatusIcon status={node.status} label={`Status: ${node.status}`} />
      ) : null}
      {!renaming && folder && node.children.length > 0 ? (
        <span className="row-badge">{node.children.length}</span>
      ) : null}
    </div>
  );
}
