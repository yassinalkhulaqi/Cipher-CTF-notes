import {
  CalendarClock,
  Code2,
  FilePlus2,
  Flag,
  LayoutDashboard,
  Network,
  PanelLeftOpen,
  Settings,
} from "lucide-react";

interface SidebarRailProps {
  hasNote: boolean;
  onExpand: () => void;
  onDashboard: () => void;
  onFlagIntel: () => void;
  onSnippets: () => void;
  onGraph: () => void;
  onTimeline: () => void;
  onNewNote: () => void;
  onSettings: () => void;
}

/**
 * Collapsed sidebar rail — icon-only navigation with tooltips, shown when the
 * sidebar is collapsed on a wide screen.
 */
export function SidebarRail({
  hasNote,
  onExpand,
  onDashboard,
  onFlagIntel,
  onSnippets,
  onGraph,
  onTimeline,
  onNewNote,
  onSettings,
}: SidebarRailProps) {
  return (
    <nav className="sidebar sidebar-rail" aria-label="Vault rail">
      <button
        type="button"
        className="rail-brand"
        onClick={onExpand}
        data-tooltip="Expand sidebar"
        aria-label="Expand sidebar"
      >
        <PanelLeftOpen />
      </button>
      <div className="rail-group">
        <button
          type="button"
          className={`rail-btn ${!hasNote ? "active" : ""}`}
          onClick={onDashboard}
          data-tooltip="Dashboard"
          aria-label="Dashboard"
          aria-current={!hasNote ? "page" : undefined}
        >
          <LayoutDashboard />
        </button>
        <button
          type="button"
          className="rail-btn"
          onClick={onFlagIntel}
          data-tooltip="Flag intelligence"
          aria-label="Flag intelligence"
        >
          <Flag />
        </button>
        <button
          type="button"
          className="rail-btn"
          onClick={onSnippets}
          data-tooltip="Snippet library"
          aria-label="Snippet library"
        >
          <Code2 />
        </button>
        <button
          type="button"
          className="rail-btn"
          onClick={onGraph}
          data-tooltip="Vault graph"
          aria-label="Vault graph"
        >
          <Network />
        </button>
        <button
          type="button"
          className="rail-btn"
          onClick={onTimeline}
          data-tooltip="Recent activity"
          aria-label="Recent activity"
        >
          <CalendarClock />
        </button>
      </div>
      <div className="rail-group rail-bottom">
        <button
          type="button"
          className="rail-btn"
          onClick={onNewNote}
          data-tooltip="New note"
          aria-label="New note"
        >
          <FilePlus2 />
        </button>
        <button
          type="button"
          className="rail-btn"
          onClick={onSettings}
          data-tooltip="Settings"
          aria-label="Settings"
        >
          <Settings />
        </button>
      </div>
    </nav>
  );
}
