import { useEffect, useRef } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { BrandMark } from "./components/BrandMark";
import { NoteWorkspace } from "./components/NoteWorkspace";
import { Sidebar } from "./components/Sidebar";
import { StatusBar } from "./components/StatusBar";
import { ToastStack } from "./components/ToastStack";
import { TopBar } from "./components/TopBar";
import { Dashboard } from "./components/Dashboard";
import { ModalHost } from "./components/modals/ModalHost";
import { useAutosaveLifecycle } from "./hooks/useAutosaveLifecycle";
import { useGlobalHotkeys } from "./hooks/useGlobalHotkeys";
import { useAppStore } from "./store/useAppStore";
import { useUiStore } from "./store/useUiStore";

export function App() {
  const boot = useAppStore((state) => state.boot);
  const bootError = useAppStore((state) => state.bootError);
  const loading = useAppStore((state) => state.loading);
  const note = useAppStore((state) => state.note);
  const focusMode = useAppStore((state) => state.focusMode);
  const bootApp = useAppStore((state) => state.bootApp);
  const mobileSidebarOpen = useUiStore((state) => state.mobileSidebarOpen);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);

  const started = useRef(false);
  useGlobalHotkeys();
  useAutosaveLifecycle();

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void bootApp();
  }, [bootApp]);

  if (loading && !boot) {
    return (
      <div className="boot-screen">
        <BrandMark />
        <div className="boot-copy">
          <h1>
            Red<em>Scribe</em>
          </h1>
          <p>Opening your vault…</p>
        </div>
        <span className="spinner" />
      </div>
    );
  }

  if (bootError) {
    return (
      <div className="boot-screen error">
        <span className="boot-error-icon">
          <AlertTriangle />
        </span>
        <div className="boot-copy">
          <h1>Could not open the vault</h1>
          <p>{bootError}</p>
        </div>
        <button
          type="button"
          className="btn primary"
          onClick={() => void bootApp()}
        >
          <RefreshCw /> Try again
        </button>
      </div>
    );
  }

  if (!boot) {
    return (
      <div className="boot-screen">
        <BrandMark />
        <span className="spinner" />
      </div>
    );
  }

  return (
    <div
      className="app-shell"
      data-focus={focusMode ? "true" : "false"}
      data-mobile-sidebar={mobileSidebarOpen ? "true" : "false"}
    >
      <TopBar />
      <div className="app-main">
        <Sidebar />
        <button
          type="button"
          className="mobile-backdrop"
          onClick={() => setMobileSidebar(false)}
          aria-label="Close the sidebar"
        />
        <main className="workspace">
          {note ? <NoteWorkspace /> : <Dashboard />}
        </main>
      </div>
      <StatusBar />
      <ModalHost />
      <ToastStack />
    </div>
  );
}
