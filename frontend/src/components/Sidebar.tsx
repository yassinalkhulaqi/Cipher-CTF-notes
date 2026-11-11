import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import {
  CalendarClock,
  ChevronsDownUp,
  ChevronsUpDown,
  Code2,
  Copy,
  FilePlus2,
  FileText,
  Flag,
  FolderPlus,
  LayoutDashboard,
  Network,
  PanelLeftClose,
  Pencil,
  Pin,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Menu, type MenuEntry } from "./Menu";
import { SidebarRail } from "./sidebar/SidebarRail";
import { TreeRow } from "./sidebar/TreeRow";
import { StatusIcon } from "./StatusIcon";
import { useFlipList } from "../motion/useFlipList";
import { useFloatingSelection } from "../motion/useFloatingSelection";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useSidebarResize } from "../hooks/useSidebarResize";
import { maxWidthQuery } from "../lib/breakpoints";
import {
  allIds,
  countNotes,
  filterTree,
  flattenVisible,
  isDescendant,
  type FlatNode,
} from "../lib/tree";
import type { TreeNode } from "../lib/types";
import { onFocusFilter } from "../lib/events";
import { modLabel, plural } from "../lib/utils";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";

interface ContextState {
  x: number;
  y: number;
  node: TreeNode;
}


export function Sidebar() {
  const tree = useAppStore((state) => state.tree);
  const nodes = useAppStore((state) => state.nodes);
  const expanded = useAppStore((state) => state.expanded);
  const selectedId = useAppStore((state) => state.selectedId);
  const filter = useAppStore((state) => state.filter);
  const sidebarWidth = useAppStore((state) => state.sidebarWidth);
  const setFilter = useAppStore((state) => state.setFilter);
  const setExpanded = useAppStore((state) => state.setExpanded);
  const toggleFolder = useAppStore((state) => state.toggleFolder);
  const openNote = useAppStore((state) => state.openNote);
  const moveNode = useAppStore((state) => state.moveNode);
  const duplicateNode = useAppStore((state) => state.duplicateNode);
  const togglePin = useAppStore((state) => state.togglePin);
  const renameNode = useAppStore((state) => state.renameNode);
  const trashNode = useAppStore((state) => state.trashNode);
  const restoreNode = useAppStore((state) => state.restoreNode);
  const loadDemo = useAppStore((state) => state.loadDemo);
  const note = useAppStore((state) => state.note);
  const closeNote = useAppStore((state) => state.closeNote);

  const openModal = useUiStore((state) => state.openModal);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const openNewFolder = useUiStore((state) => state.openNewFolder);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);
  const mobileSidebarOpen = useUiStore((state) => state.mobileSidebarOpen);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);
  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useUiStore((state) => state.setSidebarCollapsed);
  const toggleSidebarCollapsed = useUiStore(
    (state) => state.toggleSidebarCollapsed,
  );
  const mobile = useMediaQuery(maxWidthQuery("lg"));
  const collapsed = sidebarCollapsed && !mobile;

  const [context, setContext] = useState<ContextState | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | "root" | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
    const searchRef = useRef<HTMLInputElement>(null);
  const treeRef = useRef<HTMLDivElement>(null);

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
        .sort((a, b) => a.title.localeCompare(b.title))
        .slice(0, 6),
    [nodes],
  );
  const noteTotal = useMemo(() => countNotes(tree), [tree]);
  const flaggedCount = useMemo(
    () =>
      Array.from(nodes.values()).filter(
        (node) => node.kind === "note" && !node.trashed && node.flag,
      ).length,
    [nodes],
  );
  const folderIds = useMemo(
    () =>
      Array.from(nodes.values())
        .filter((node) => node.kind === "folder")
        .map((node) => node.id),
    [nodes],
  );
  const anyExpanded = folderIds.some((id) => expanded.has(id));

  const flipSignature = useMemo(
    () => rows.map((row) => row.node.id).join(":"),
    [rows],
  );
  const selectionSignature = useMemo(
    () =>
      `${selectedId ?? "none"}:${filter}:${rows
        .map((row) => row.node.id)
        .join(":")}:${pinned.map((node) => node.id).join(":")}`,
    [selectedId, filter, rows, pinned],
  );

  useFlipList(treeRef, flipSignature, {
    selector: ".tree > .tree-row[data-node-id]",
  });
  const selection = useFloatingSelection(
    treeRef,
    selectedId,
    selectionSignature,
  );

  useEffect(
    () =>
      onFocusFilter(() => {
        searchRef.current?.focus();
        searchRef.current?.select();
      }),
    [],
  );

  const closeMobile = () => setMobileSidebar(false);

  const goDashboard = () => {
    closeMobile();
    if (!note) return;
    void closeNote().catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not close the note",
        "error",
      ),
    );
  };

  const handleSelect = (id: number) => {
    closeMobile();
    void openNote(id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const focusRow = (id: number) => {
    window.requestAnimationFrame(() => {
      const element = treeRef.current?.querySelector<HTMLElement>(
        `[data-node-id="${id}"]`,
      );
      element?.focus();
    });
  };

  const startRename = (node: TreeNode) => {
    setContext(null);
    setRenamingId(node.id);
  };

  const commitRename = async (id: number, title: string) => {
    setRenamingId(null);
    try {
      await renameNode(id, title);
      toast("Renamed", "success");
      focusRow(id);
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not rename item",
        "error",
      );
    }
  };

  const handleKeyNavigate = (
    event: KeyboardEvent<HTMLDivElement>,
    row: FlatNode,
  ) => {
    const index = rows.findIndex((item) => item.node.id === row.node.id);
    if (index < 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      const next = rows[Math.min(rows.length - 1, index + 1)];
      if (next) focusRow(next.node.id);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      const previous = rows[Math.max(0, index - 1)];
      if (previous) focusRow(previous.node.id);
    } else if (event.key === "Home") {
      event.preventDefault();
      const first = rows[0];
      if (first) focusRow(first.node.id);
    } else if (event.key === "End") {
      event.preventDefault();
      const last = rows[rows.length - 1];
      if (last) focusRow(last.node.id);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      if (row.node.kind === "folder" && !expanded.has(row.node.id)) {
        toggleFolder(row.node.id);
      } else {
        const next = rows[index + 1];
        if (next && next.depth > row.depth) focusRow(next.node.id);
      }
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (row.node.kind === "folder" && expanded.has(row.node.id)) {
        toggleFolder(row.node.id);
      } else if (row.node.parent_id !== null) {
        focusRow(row.node.parent_id);
      }
    }
  };

  const collapseAll = () => {
    if (anyExpanded) setExpanded([]);
    else setExpanded(folderIds);
  };

  const confirmTrash = (node: TreeNode) => {
    askConfirm({
      title: "Move to trash",
      message: `Move â€œ${node.title}â€‌${node.kind === "folder" ? " and everything inside it" : ""} to the trash?`,
      confirmLabel: "Move to trash",
      danger: true,
      action: async () => {
        try {
          const removed = await trashNode(node.id);
          toast(
            removed > 1
              ? `Moved ${plural(removed, "item")} to trash`
              : "Moved to trash",
            "default",
            { label: "Undo", run: () => restoreNode(node.id) },
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
    const items: MenuEntry[] = [
      {
        label: "Rename",
        icon: Pencil,
        shortcut: "F2",
        onSelect: () => startRename(node),
      },
      {
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
      },
    ];
    if (node.kind === "folder") {
      items.unshift(
        {
          label: "New note inside",
          icon: FilePlus2,
          onSelect: () => openNewNote(node.id),
        },
        {
          label: "New folder inside",
          icon: FolderPlus,
          onSelect: () => openNewFolder(node.id),
        },
      );
    } else {
      items.unshift({
        label: "New note",
        icon: FilePlus2,
        onSelect: () => openNewNote(node.parent_id),
      });
      items.push({
        label: node.pinned ? "Unpin note" : "Pin note",
        icon: Pin,
        shortcut: `${modLabel()} Shift P`,
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
      title: "Add the sample workspace",
      message:
        "Adds a small set of demonstration challenges, folders, and flags to this vault. Existing notes are left untouched.",
      confirmLabel: "Add samples",
      danger: false,
      action: async () => {
        try {
          await loadDemo();
          toast("Sample workspace added", "success");
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not load the demo",
            "error",
          );
        }
      },
    });
  };

  const { draggingSash, startResize, resizeKey } = useSidebarResize();

  if (collapsed) {
    return (
      <SidebarRail
        hasNote={note !== null}
        onExpand={() => setSidebarCollapsed(false)}
        onDashboard={goDashboard}
        onFlagIntel={() => {
          closeMobile();
          openModal("flag-intel");
        }}
        onSnippets={() => {
          closeMobile();
          openModal("snippets");
        }}
        onGraph={() => {
          closeMobile();
          openModal("graph");
        }}
        onTimeline={() => {
          closeMobile();
          openModal("timeline");
        }}
        onNewNote={() => openNewNote()}
        onSettings={() => openModal("settings")}
      />
    );
  }

  return (
    <nav
      className="sidebar"
      aria-label="Vault"
      data-open={mobileSidebarOpen}
      style={{ width: sidebarWidth }}
    >
      <div
        className={`sidebar-head ${dropTarget === "root" ? "drop-target" : ""}`}
        title="Drop here to move an item to the vault root"
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
        <div className="sidebar-tools">
          <button
            type="button"
            className="icon-btn sm"
            onClick={toggleSidebarCollapsed}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose />
          </button>
          <button
            type="button"
            className="icon-btn sm"
            onClick={collapseAll}
            title={anyExpanded ? "Collapse all folders" : "Expand all folders"}
            aria-label={
              anyExpanded ? "Collapse all folders" : "Expand all folders"
            }
          >
            {anyExpanded ? <ChevronsDownUp /> : <ChevronsUpDown />}
          </button>
          <button
            type="button"
            className="icon-btn sm"
            onClick={() => openNewFolder()}
            title={`New folder (${modLabel()}+Shift+N)`}
            aria-label="New folder"
          >
            <FolderPlus />
          </button>
          <button
            type="button"
            className="icon-btn sm"
            onClick={() => openModal("trash")}
            title="Open trash"
            aria-label="Open trash"
          >
            <Trash2 />
          </button>
        </div>
      </div>

      <div className="sidebar-nav" aria-label="Workspace views">
        <button
          type="button"
          className={`sidebar-nav-row ${!note ? "active" : ""}`}
          onClick={goDashboard}
          aria-current={!note ? "page" : undefined}
        >
          <LayoutDashboard />
          <span>Dashboard</span>
        </button>
        <button
          type="button"
          className="sidebar-nav-row"
          onClick={() => {
            closeMobile();
            openModal("flag-intel");
          }}
        >
          <Flag />
          <span>Flag intelligence</span>
          {flaggedCount > 0 ? (
            <span className="sidebar-nav-count">{flaggedCount}</span>
          ) : null}
        </button>
        <button
          type="button"
          className="sidebar-nav-row"
          onClick={() => {
            closeMobile();
            openModal("snippets");
          }}
        >
          <Code2 />
          <span>Snippet library</span>
        </button>
        <button
          type="button"
          className="sidebar-nav-row"
          onClick={() => {
            closeMobile();
            openModal("graph");
          }}
        >
          <Network />
          <span>Vault graph</span>
        </button>
        <button
          type="button"
          className="sidebar-nav-row"
          onClick={() => {
            closeMobile();
            openModal("timeline");
          }}
        >
          <CalendarClock />
          <span>Recent activity</span>
        </button>
      </div>

      <div className="sidebar-search">
        <Search />
        <input
          ref={searchRef}
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter notes, tags, targetsâ€¦"
          spellCheck={false}
          autoComplete="off"
          aria-label="Filter vault"
        />
        {filter ? (
          <button
            type="button"
            className="icon-btn sm"
            onClick={() => {
              setFilter("");
              searchRef.current?.focus();
            }}
            aria-label="Clear filter"
          >
            <X />
          </button>
        ) : null}
      </div>

      <div
        ref={treeRef}
        className="tree"
        role="tree"
        aria-label="Vault tree"
        data-selection={selection.active ? "true" : "false"}
      >
        <span
          className={`tree-selection ${selection.active ? "is-active" : ""}`}
          style={selection.style}
          aria-hidden="true"
        />
        {!forceOpen && pinned.length > 0 ? (
          <div className="tree-pinned">
            <div className="list-label">Pinned</div>
            {pinned.map((node) => (
              <button
                key={node.id}
                type="button"
                role="treeitem"
                aria-selected={selectedId === node.id}
                aria-level={1}
                tabIndex={0}
                className={`tree-row ${selectedId === node.id ? "selected" : ""}`}
                style={{ paddingLeft: "5px" }}
                data-node-id={node.id}
                onClick={() => handleSelect(node.id)}
                title={node.path || node.title}
              >
                <span className="chevron" />
                <span className="node-icon">
                  <FileText />
                </span>
                <span className="node-title">{node.title}</span>
                <StatusIcon status={node.status} />
                <span className="row-pin">
                  <Pin />
                </span>
              </button>
            ))}
            <div className="tree-divider" />
          </div>
        ) : null}

        {rows.map((row, index) => (
          <TreeRow
            key={row.node.id}
            row={row}
            selected={selectedId === row.node.id}
            focusable={
              selectedId === row.node.id || (selectedId === null && index === 0)
            }
            expanded={expanded.has(row.node.id)}
            dragging={draggingId === row.node.id}
            dropTarget={dropTarget === row.node.id}
            renaming={renamingId === row.node.id}
            onToggle={toggleFolder}
            onSelect={handleSelect}
            onRename={commitRename}
            onRenameDone={() => setRenamingId(null)}
            onKeyNavigate={handleKeyNavigate}
            onStartRename={startRename}
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
                Start with a note or add the samples.
              </div>
              <button
                type="button"
                className="btn ghost tiny"
                onClick={() => openNewNote(null)}
              >
                <FilePlus2 /> New note
              </button>
              <button type="button" className="link-btn" onClick={handleDemo}>
                Add sample workspace
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

      <div
        className={`sidebar-resizer ${draggingSash ? "dragging" : ""}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuemin={220}
        aria-valuemax={480}
        aria-valuenow={Math.round(sidebarWidth)}
        tabIndex={0}
        onPointerDown={startResize}
        onKeyDown={resizeKey}
      />

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
