import {
  useMemo,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import {
  ChevronRight,
  Copy,
  FilePlus2,
  FileText,
  Flag,
  Folder,
  FolderOpen,
  FolderPlus,
  Pencil,
  Pin,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Menu, type MenuEntry } from "./Menu";
import {
  allIds,
  countNotes,
  filterTree,
  flattenVisible,
  isDescendant,
  type FlatNode,
} from "../lib/tree";
import type { TreeNode } from "../lib/types";
import { plural } from "../lib/utils";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";

interface ContextState {
  x: number;
  y: number;
  node: TreeNode;
}

interface TreeRowProps {
  row: FlatNode;
  selected: boolean;
  expanded: boolean;
  dragging: boolean;
  dropTarget: boolean;
  onToggle: (id: number) => void;
  onSelect: (id: number) => void;
  onContext: (event: MouseEvent<HTMLDivElement>, node: TreeNode) => void;
  onDragStart: (event: DragEvent<HTMLDivElement>, node: TreeNode) => void;
  onDragEnd: () => void;
  onDragOver: (event: DragEvent<HTMLDivElement>, node: TreeNode) => void;
  onDrop: (event: DragEvent<HTMLDivElement>, node: TreeNode) => void;
}

function TreeRow({
  row,
  selected,
  expanded,
  dragging,
  dropTarget,
  onToggle,
  onSelect,
  onContext,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}: TreeRowProps) {
  const { node, depth } = row;
  const folder = node.kind === "folder";
  const open = folder && expanded;

  const activate = () => {
    if (folder) onToggle(node.id);
    else onSelect(node.id);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate();
    }
    if (event.key === "ArrowRight" && folder && !open) {
      event.preventDefault();
      onToggle(node.id);
    }
    if (event.key === "ArrowLeft" && folder && open) {
      event.preventDefault();
      onToggle(node.id);
    }
  };

  return (
    <div
      className={`tree-row ${selected ? "selected" : ""} ${dragging ? "dragging" : ""} ${
        dropTarget ? "drop-target" : ""
      }`}
      style={{ paddingLeft: `${6 + depth * 15}px` }}
      role="treeitem"
      aria-selected={selected}
      aria-expanded={folder ? open : undefined}
      tabIndex={0}
      title={node.path || node.title}
      draggable
      onClick={activate}
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
      <span className={`node-title ${folder ? "folder" : ""}`}>
        {node.title}
      </span>
      {node.pinned ? (
        <span className="row-pin" title="Pinned">
          <Pin />
        </span>
      ) : null}
      {node.flag ? (
        <span className="row-flag" title={node.flag}>
          <Flag />
        </span>
      ) : null}
      {!folder && node.status !== "todo" ? (
        <span className={`dot ${node.status}`} title={node.status} />
      ) : null}
      {folder && node.children.length > 0 ? (
        <span className="row-badge">{node.children.length}</span>
      ) : null}
    </div>
  );
}

export function Sidebar() {
  const tree = useAppStore((state) => state.tree);
  const nodes = useAppStore((state) => state.nodes);
  const expanded = useAppStore((state) => state.expanded);
  const selectedId = useAppStore((state) => state.selectedId);
  const filter = useAppStore((state) => state.filter);
  const sidebarWidth = useAppStore((state) => state.sidebarWidth);
  const setFilter = useAppStore((state) => state.setFilter);
  const toggleFolder = useAppStore((state) => state.toggleFolder);
  const openNote = useAppStore((state) => state.openNote);
  const moveNode = useAppStore((state) => state.moveNode);
  const duplicateNode = useAppStore((state) => state.duplicateNode);
  const togglePin = useAppStore((state) => state.togglePin);
  const trashNode = useAppStore((state) => state.trashNode);
  const loadDemo = useAppStore((state) => state.loadDemo);

  const openModal = useUiStore((state) => state.openModal);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const openNewFolder = useUiStore((state) => state.openNewFolder);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);
  const mobileSidebarOpen = useUiStore((state) => state.mobileSidebarOpen);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);

  const [context, setContext] = useState<ContextState | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | "root" | null>(null);

  const filtered = useMemo(() => filterTree(tree, filter), [tree, filter]);
  const forceOpen = filter.trim().length > 0;
  const rows = useMemo(
    () =>
      flattenVisible(
        filtered,
        forceOpen ? new Set(allIds(filtered)) : expanded,
      ),
    [filtered, forceOpen, expanded],
  );
  const pinned = useMemo(
    () =>
      Array.from(nodes.values())
        .filter((node) => node.kind === "note" && node.pinned)
        .slice(0, 6),
    [nodes],
  );
  const noteTotal = useMemo(() => countNotes(tree), [tree]);

  const closeMobile = () => setMobileSidebar(false);

  const handleSelect = (id: number) => {
    closeMobile();
    void openNote(id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const confirmTrash = (node: TreeNode) => {
    askConfirm({
      title: "Move to trash",
      message: `Move “${node.title}”${node.kind === "folder" ? " and everything inside it" : ""} to the trash?`,
      confirmLabel: "Move to trash",
      danger: true,
      action: async () => {
        try {
          const removed = await trashNode(node.id);
          toast(
            removed > 1
              ? `Moved ${plural(removed, "item")} to trash`
              : "Moved to trash",
          );
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not move item",
            "error",
          );
        }
      },
    });
  };

  const contextItems = (node: TreeNode): MenuEntry[] => {
    const items: MenuEntry[] = [];
    if (node.kind === "folder") {
      items.push({
        label: "New note inside",
        icon: FilePlus2,
        onSelect: () => openNewNote(node.id),
      });
      items.push({
        label: "New folder inside",
        icon: FolderPlus,
        onSelect: () => openNewFolder(node.id),
      });
    } else {
      items.push({
        label: "New note",
        icon: FilePlus2,
        onSelect: () => openNewNote(node.parent_id),
      });
      items.push({
        label: "Rename title",
        icon: Pencil,
        shortcut: "F2",
        onSelect: () => {
          void openNote(node.id).then(() => {
            window.setTimeout(() => {
              const input =
                document.querySelector<HTMLInputElement>(".title-input");
              input?.focus();
              input?.select();
            }, 40);
          });
        },
      });
    }
    items.push({
      label: "Duplicate",
      icon: Copy,
      onSelect: () => {
        void duplicateNode(node.id).then(
          () => toast("Duplicated", "success"),
          (error: unknown) =>
            toast(
              error instanceof Error ? error.message : "Could not duplicate",
              "error",
            ),
        );
      },
    });
    if (node.kind === "note") {
      items.push({
        label: node.pinned ? "Unpin note" : "Pin note",
        icon: Pin,
        shortcut: "Ctrl Shift P",
        onSelect: () => {
          void togglePin(node.id).then(
            () =>
              toast(node.pinned ? "Note unpinned" : "Note pinned", "success"),
            (error: unknown) =>
              toast(
                error instanceof Error ? error.message : "Could not update pin",
                "error",
              ),
          );
        },
      });
    }
    items.push("separator");
    items.push({
      label: "Move to trash",
      icon: Trash2,
      shortcut: "Del",
      danger: true,
      onSelect: () => confirmTrash(node),
    });
    return items;
  };

  const startDrag = (event: DragEvent<HTMLDivElement>, node: TreeNode) => {
    setDraggingId(node.id);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(node.id));
  };

  const finishDrag = () => {
    setDraggingId(null);
    setDropTarget(null);
  };

  const canDrop = (node: TreeNode): boolean => {
    if (draggingId === null) return false;
    if (node.id === draggingId) return false;
    return !isDescendant(nodes, node.id, draggingId);
  };

  const overNode = (event: DragEvent<HTMLDivElement>, node: TreeNode) => {
    if (!canDrop(node)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setDropTarget(node.id);
  };

  const dropOnNode = async (
    event: DragEvent<HTMLDivElement>,
    node: TreeNode,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    if (!canDrop(node) || draggingId === null) {
      finishDrag();
      return;
    }
    const id = draggingId;
    const parentId = node.kind === "folder" ? node.id : node.parent_id;
    const beforeId = node.kind === "folder" ? null : node.id;
    finishDrag();
    try {
      await moveNode(id, parentId, beforeId);
      toast("Moved in vault", "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not move item",
        "error",
      );
    }
  };

  const dropOnRoot = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (draggingId === null) return;
    const id = draggingId;
    finishDrag();
    try {
      await moveNode(id, null, null);
      toast("Moved to vault root", "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not move item",
        "error",
      );
    }
  };

  const handleDemo = () => {
    askConfirm({
      title: "Load the demo vault",
      message:
        "This adds a small set of sample challenges and folders to your vault.",
      confirmLabel: "Load demo",
      danger: false,
      action: async () => {
        try {
          await loadDemo();
          toast("Demo vault loaded", "success");
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not load the demo",
            "error",
          );
        }
      },
    });
  };

  return (
    <nav
      className="sidebar"
      aria-label="Vault"
      data-open={mobileSidebarOpen}
      style={{ width: sidebarWidth }}
    >
      <div
        className={`sidebar-head ${dropTarget === "root" ? "drop-target" : ""}`}
        title="Drag here to move an item to the vault root"
        onDragOver={(event) => {
          if (draggingId === null) return;
          event.preventDefault();
          setDropTarget("root");
        }}
        onDragLeave={() => setDropTarget(null)}
        onDrop={dropOnRoot}
      >
        <div className="sidebar-head-copy">
          <span className="eyebrow">Vault</span>
          <span className="sidebar-count">{plural(noteTotal, "note")}</span>
        </div>
        <button
          className="icon-btn sm"
          type="button"
          onClick={() => openModal("trash")}
          title="Open trash"
          aria-label="Open trash"
        >
          <Trash2 />
        </button>
      </div>

      <div className="sidebar-search">
        <Search />
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter this vault…"
          spellCheck={false}
          autoComplete="off"
          aria-label="Filter vault"
        />
        {filter ? (
          <button
            type="button"
            className="icon-btn sm"
            onClick={() => setFilter("")}
            aria-label="Clear filter"
          >
            <X />
          </button>
        ) : null}
      </div>

      <div className="tree" role="tree" aria-label="Vault tree">
        {!forceOpen && pinned.length > 0 ? (
          <div className="tree-pinned">
            <div className="list-label">Pinned</div>
            {pinned.map((node) => (
              <button
                key={node.id}
                type="button"
                className={`tree-row ${selectedId === node.id ? "selected" : ""}`}
                style={{ paddingLeft: "6px" }}
                onClick={() => handleSelect(node.id)}
                title={node.path || node.title}
              >
                <span className="chevron" />
                <span className="node-icon">
                  <FileText />
                </span>
                <span className="node-title">{node.title}</span>
                <span className="row-pin">
                  <Pin />
                </span>
              </button>
            ))}
            <div className="tree-divider" />
          </div>
        ) : null}

        {rows.map((row) => (
          <TreeRow
            key={row.node.id}
            row={row}
            selected={selectedId === row.node.id}
            expanded={expanded.has(row.node.id)}
            dragging={draggingId === row.node.id}
            dropTarget={dropTarget === row.node.id}
            onToggle={toggleFolder}
            onSelect={handleSelect}
            onContext={(event, node) => {
              event.preventDefault();
              if (node.kind === "note" && selectedId !== node.id) {
                void openNote(node.id).catch(() => undefined);
              }
              setContext({ x: event.clientX, y: event.clientY, node });
            }}
            onDragStart={startDrag}
            onDragEnd={finishDrag}
            onDragOver={overNode}
            onDrop={(event, node) => {
              void dropOnNode(event, node);
            }}
          />
        ))}

        {rows.length === 0 ? (
          filter ? (
            <div className="tree-empty">
              <Search />
              <div>
                No notes match <strong>{filter}</strong>
              </div>
              <button
                type="button"
                className="link-btn"
                onClick={() => setFilter("")}
              >
                Clear filter
              </button>
            </div>
          ) : (
            <div className="tree-empty">
              <Sparkles />
              <div>
                Your vault is empty.
                <br />
                Start with a note or explore the demo.
              </div>
              <button
                type="button"
                className="btn ghost tiny"
                onClick={() => openNewNote(null)}
              >
                <FilePlus2 /> New note
              </button>
              <button type="button" className="link-btn" onClick={handleDemo}>
                Load demo vault
              </button>
            </div>
          )
        ) : null}
      </div>

      <div className="sidebar-foot">
        <button
          className="btn ghost sm"
          type="button"
          onClick={() => openNewNote()}
        >
          <FilePlus2 />
          Note
        </button>
        <button
          className="btn ghost sm"
          type="button"
          onClick={() => openNewFolder()}
        >
          <FolderPlus />
          Folder
        </button>
      </div>

      {context ? (
        <Menu
          x={context.x}
          y={context.y}
          items={contextItems(context.node)}
          onClose={() => setContext(null)}
          label={`Actions for ${context.node.title}`}
        />
      ) : null}
    </nav>
  );
}
