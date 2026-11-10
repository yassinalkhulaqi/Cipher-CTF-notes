import {
  ChevronRight,
  CircleHelp,
  Code2,
  Command,
  Flag,
  HardDrive,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  Plus,
  Search,
  Settings,
  Sun,
  Zap,
} from "lucide-react";
import { BrandMark } from "./BrandMark";
import { startThemeTransition } from "../lib/viewTransition";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";
import { baseName, modLabel } from "../lib/utils";

export function TopBar() {
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const closeNote = useAppStore((state) => state.closeNote);
  const boot = useAppStore((state) => state.boot);
  const note = useAppStore((state) => state.note);
  const hasNote = note !== null;
  const openModal = useUiStore((state) => state.openModal);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const toast = useUiStore((state) => state.toast);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);
  const mobileSidebarOpen = useUiStore((state) => state.mobileSidebarOpen);
  const toggleMobileSidebar = () => setMobileSidebar(!mobileSidebarOpen);

  const vaultName = boot ? baseName(boot.vault_path) || "Vault" : "Vault";

  const toggleTheme = (x: number, y: number) => {
    const next = theme === "dark" ? "light" : "dark";
    startThemeTransition({ x, y }, () => setTheme(next));
  };

  const goHome = () => {
    setMobileSidebar(false);
    if (hasNote) {
      void closeNote().catch((error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not close the note",
          "error",
        ),
      );
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button
          className="icon-btn mobile-only"
          type="button"
          onClick={toggleMobileSidebar}
          aria-label="Toggle vault sidebar"
        >
          <Menu />
        </button>
        <button
          className="brand"
          type="button"
          onClick={goHome}
          title="Open the research desk"
        >
          <BrandMark />
          <span className="brand-name">
            Red<em>Scribe</em>
          </span>
        </button>
        {boot ? (
          <span
            className="vault-pill"
            title={`${boot.vault_path}\nLocal SQLite vault`}
          >
            <span className="dot" />
            <HardDrive />
            {vaultName}
          </span>
        ) : null}
        <span className="topbar-divider desktop-only" />
        <span
          className="topbar-context desktop-only"
          title={note ? note.path : "Research desk"}
        >
          <ChevronRight />
          <span>{note ? note.title : "Research desk"}</span>
        </span>
      </div>

      <div className="topbar-center">
        <button
          className="command-trigger"
          type="button"
          onClick={() => openModal("palette")}
          data-tooltip={`Quick switch (${modLabel()}+P)`}
        >
          <Command />
          <span>Jump to a note or run a command…</span>
          <kbd>{modLabel()} P</kbd>
        </button>
      </div>

      <div className="topbar-actions">
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("search")}
          data-tooltip={`Full-text search (${modLabel()}+Shift+F)`}
          aria-label="Full-text search"
        >
          <Search />
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("quick-capture")}
          data-tooltip={`Quick capture (${modLabel()}+Shift+Q)`}
          aria-label="Quick capture"
        >
          <Zap />
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("flag-intel")}
          data-tooltip={`Flag intelligence (${modLabel()}+Shift+I)`}
          aria-label="Flag intelligence"
        >
          <Flag />
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("snippets")}
          data-tooltip={`Snippet library (${modLabel()}+Shift+S)`}
          aria-label="Snippet library"
        >
          <Code2 />
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("dashboard")}
          data-tooltip={`Vault insights (${modLabel()}+Shift+D)`}
          aria-label="Vault insights"
        >
          <LayoutDashboard />
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("graph")}
          data-tooltip={`Vault graph (${modLabel()}+Shift+G)`}
          aria-label="Vault graph"
        >
          <Network />
        </button>
        <span className="topbar-divider desktop-only" />
        <button
          className="btn primary topbar-new"
          type="button"
          onClick={() => openNewNote()}
          data-tooltip={`New note (${modLabel()}+N for quick note)`}
        >
          <Plus />
          <span className="new-note-label">New note</span>
        </button>
        <button
          className="icon-btn theme-toggle"
          type="button"
          onClick={(event) => toggleTheme(event.clientX, event.clientY)}
          data-tooltip={
            theme === "dark" ? "Switch to light theme" : "Switch to dark theme"
          }
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun /> : <Moon />}
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("settings")}
          data-tooltip={`Settings (${modLabel()}+,)`}
          aria-label="Settings"
        >
          <Settings />
        </button>
        <button
          className="icon-btn desktop-only"
          type="button"
          onClick={() => openModal("help")}
          data-tooltip="Keyboard shortcuts (F1)"
          aria-label="Keyboard shortcuts"
        >
          <CircleHelp />
        </button>
      </div>
    </header>
  );
}
