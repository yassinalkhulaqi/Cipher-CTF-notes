/** Multi-pane workspace canvas with keyboard and pointer resizing. */

import type { CSSProperties, ReactNode } from "react";

import { PaneHeader } from "./PaneHeader";
import type { NavNode, PaneNode, PaneSpec, WorkspaceSnapshot } from "./types";
import { makePane } from "./workspace";

export interface WorkspaceCanvasProps {
  snapshot: WorkspaceSnapshot;
  crumbsByPane?: Record<string, NavNode[]>;
  onActivate: (paneId: string) => void;
  onResize: (paneId: string, size: number) => void;
  onSplit: (paneId: string) => void;
  onClose: (paneId: string) => void;
  onCommandBar: (paneId: string) => void;
  children?: (pane: PaneSpec) => ReactNode;
}

function firstPaneId(node: PaneNode): string {
  if (node.pane) return node.pane.id;
  return firstPaneId(
    node.children?.[0] ?? { pane: makePane("pane:main", "Main") },
  );
}

export function WorkspaceCanvas({
  snapshot,
  crumbsByPane = {},
  onActivate,
  onResize,
  onSplit,
  onClose,
  onCommandBar,
  children,
}: WorkspaceCanvasProps) {
  const renderNode = (node: PaneNode, depth: number): ReactNode => {
    if (node.pane) {
      const pane = node.pane;
      const active = pane.id === snapshot.active_pane;
      return (
        <section
          className="v3c-pane"
          data-testid={`pane-${pane.id}`}
          data-pane={pane.id}
          data-active={active}
          data-depth={depth}
          aria-label={`${pane.title} pane`}
        >
          <PaneHeader
            pane={pane}
            crumbs={crumbsByPane[pane.id] ?? []}
            active={active}
            onActivate={() => onActivate(pane.id)}
            onClose={() => onClose(pane.id)}
            onSplit={() => onSplit(pane.id)}
            onCommandBar={() => onCommandBar(pane.id)}
          />
          <div className="v3c-pane__body">
            {children ? (
              children(pane)
            ) : (
              <p className="v3c-pane__empty">
                {pane.context_ref || "No context selected"}
              </p>
            )}
          </div>
        </section>
      );
    }
    const orientation = node.orientation ?? "vertical";
    const ratio = node.ratio ?? 0.5;
    const childrenNodes = node.children ?? [];
    const flexDirection: CSSProperties["flexDirection"] =
      orientation === "horizontal" ? "row" : "column";
    return (
      <div
        className="v3c-split"
        data-orientation={orientation}
        style={{ flexDirection }}
      >
        <div
          className="v3c-split__branch"
          style={{ flexBasis: `${ratio * 100}%` }}
        >
          {renderNode(childrenNodes[0] ?? {}, depth + 1)}
        </div>
        <div
          className="v3c-splitter"
          role="separator"
          aria-orientation={
            orientation === "horizontal" ? "vertical" : "horizontal"
          }
        >
          <input
            type="range"
            aria-label="Resize panes"
            min={10}
            max={90}
            value={Math.round(ratio * 100)}
            onChange={(event) =>
              onResize(
                firstPaneId(childrenNodes[0] ?? {}),
                Number(event.target.value) / 100,
              )
            }
          />
        </div>
        <div
          className="v3c-split__branch"
          style={{ flexBasis: `${(1 - ratio) * 100}%` }}
        >
          {renderNode(childrenNodes[1] ?? {}, depth + 1)}
        </div>
      </div>
    );
  };

  return (
    <div
      className="v3c-canvas"
      data-testid="workspace-canvas"
      data-active={snapshot.active_pane}
    >
      {renderNode(snapshot.tree.root, 0)}
    </div>
  );
}
