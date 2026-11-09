import { useEffect, useRef } from "react";
import { BootScreen } from "./components/BootScreen";
import { NoteWorkspace } from "./components/NoteWorkspace";
import { Sidebar } from "./components/Sidebar";
import { StatusBar } from "./components/StatusBar";
import { ToastStack } from "./components/ToastStack";
import { TooltipHost } from "./components/TooltipHost";
import { TopBar } from "./components/TopBar";
import { Dashboard } from "./components/Dashboard";
import { OnboardingTour } from "./components/modals/OnboardingTour";
import { ModalHost } from "./components/modals/ModalHost";
import { useAutosaveLifecycle } from "./hooks/useAutosaveLifecycle";
import { useGlobalHotkeys } from "./hooks/useGlobalHotkeys";
import { Aurora } from "./motion/Aurora";
import { CursorGlow } from "./motion/CursorGlow";
import { useCardTilt } from "./motion/useCardTilt";
import { useGlobalRipple } from "./motion/useGlobalRipple";
import { useScrollReveal } from "./motion/useScrollReveal";
import { useAppStore } from "./store/useAppStore";
import { useUiStore } from "./store/useUiStore";

export function App() {
  const boot = useAppStore((state) => state.boot);
  const bootError = useAppStore((state) => state.bootError);
  const note = useAppStore((state) => state.note);
  const focusMode = useAppStore((state) => state.focusMode);
  const bootApp = useAppStore((state) => state.bootApp);
  const mobileSidebarOpen = useUiStore((state) => state.mobileSidebarOpen);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);

  const started = useRef(false);
  useGlobalHotkeys();
  useAutosaveLifecycle();
  useGlobalRipple();
  useCardTilt();
  useScrollReveal();

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void bootApp();
  }, [bootApp]);

  if (!boot) {
    return (
      <BootScreen
        error={bootError}
        onRetry={
          bootError
            ? () => {
                void bootApp();
              }
            : undefined
        }
      />
    );
  }

  const onboardingShown = boot?.onboarding_seen === "1";

  return (
    <div
      className="app-shell"
      data-focus={focusMode ? "true" : "false"}
      data-mobile-sidebar={mobileSidebarOpen ? "true" : "false"}
    >
      <a className="skip-link" href="#main-content">
        Skip to workspace
      </a>
      <Aurora />
      <CursorGlow />
      <TopBar />
      <div className="app-main">
        <Sidebar />
        <button
          type="button"
          className="mobile-backdrop"
          onClick={() => setMobileSidebar(false)}
          aria-label="Close the sidebar"
        />
        <main className="workspace" id="main-content" tabIndex={-1}>
          <div className="motion-page" key={note ? `note-${note.id}` : "desk"}>
            {note ? <NoteWorkspace /> : <Dashboard />}
          </div>
        </main>
      </div>
      <StatusBar />
      <ModalHost />
      <ToastStack />
      <TooltipHost />
      {onboardingShown !== true && <OnboardingTour />}
    </div>
  );
}
