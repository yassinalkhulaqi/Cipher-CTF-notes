import { useEffect } from "react";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(
    target.closest(
      "input, textarea, select, [contenteditable='true'], [role='textbox']",
    ),
  );
}

export function useGlobalHotkeys(): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      const ui = useUiStore.getState();
      const app = useAppStore.getState();

      if (event.key === "Escape") {
        if (ui.modal) {
          event.preventDefault();
          ui.closeModal();
        } else if (ui.findMode) {
          event.preventDefault();
          ui.closeFind();
        }
        return;
      }

      if (ui.modal) {
        if (event.key === "F1" && ui.modal === "help") {
          event.preventDefault();
          ui.closeModal();
        }
        return;
      }

      if (event.key === "F1") {
        event.preventDefault();
        ui.openModal("help");
        return;
      }

      if (mod && event.shiftKey && key === "p") {
        event.preventDefault();
        void app.togglePin();
        return;
      }
      if (mod && event.shiftKey && key === "f") {
        event.preventDefault();
        ui.openModal("search");
        return;
      }
      if (mod && event.shiftKey && key === "s") {
        event.preventDefault();
        ui.openModal("snippets");
        return;
      }
      if (mod && event.shiftKey && key === "g") {
        event.preventDefault();
        ui.openModal("graph");
        return;
      }
      if (mod && event.shiftKey && key === "t") {
        event.preventDefault();
        ui.openModal("timeline");
        return;
      }
      if (mod && event.shiftKey && key === "q") {
        event.preventDefault();
        ui.openModal("quick-capture");
        return;
      }
      if (mod && event.shiftKey && key === "d") {
        event.preventDefault();
        ui.openModal("dashboard");
        return;
      }
      if (mod && event.shiftKey && key === "i") {
        event.preventDefault();
        ui.openModal("flag-intel");
        return;
      }
      if (mod && event.shiftKey && key === "j") {
        event.preventDefault();
        if (!app.note) {
          ui.toast("Open a note to use the inspector", "default");
          return;
        }
        ui.toggleInspector();
        return;
      }
      if (mod && event.shiftKey && key === "b") {
        event.preventDefault();
        ui.toggleSidebarCollapsed();
        return;
      }
      if (mod && event.shiftKey && key === "n") {
        event.preventDefault();
        ui.openNewFolder();
        return;
      }
      if (mod && event.shiftKey && key === "l") {
        event.preventDefault();
        app.toggleFocusMode();
        return;
      }
      if (mod && !event.shiftKey && key === "p") {
        event.preventDefault();
        ui.openModal("palette");
        return;
      }
      if (mod && !event.shiftKey && key === "n") {
        event.preventDefault();
        void app.quickNote().then(
          (node) => ui.toast(`Created “${node.title}”`, "success"),
          (error: unknown) =>
            ui.toast(
              error instanceof Error ? error.message : "Could not create note",
              "error",
            ),
        );
        return;
      }
      if (mod && key === "e") {
        event.preventDefault();
        app.cycleView();
        return;
      }
      if (mod && key === "f") {
        event.preventDefault();
        ui.openFind("find");
        return;
      }
      if (mod && key === "h") {
        event.preventDefault();
        ui.openFind("replace");
        return;
      }
      if (mod && key === "s") {
        event.preventDefault();
        if (!app.note) {
          ui.toast("Open a note to save", "default");
          return;
        }
        if (!app.dirty) {
          ui.toast("No unsaved changes", "default");
          return;
        }
        void app.saveNow().then(
          () => ui.toast("Note saved", "success"),
          (error: unknown) =>
            ui.toast(
              error instanceof Error ? error.message : "Could not save note",
              "error",
            ),
        );
        return;
      }
      if (mod && key === ",") {
        event.preventDefault();
        ui.openModal("settings");
        return;
      }
      if (event.key === "F2") {
        event.preventDefault();
        if (app.note) ui.openModal("properties");
        return;
      }

      if (isTyping(event.target)) return;

      if (event.key === "Delete" && app.selectedId !== null) {
        const node = app.nodes.get(app.selectedId);
        if (!node) return;
        ui.askConfirm({
          title: "Move to trash",
          message: `Move “${node.title}”${node.kind === "folder" ? " and everything inside it" : ""} to the trash?`,
          confirmLabel: "Move to trash",
          danger: true,
          action: async () => {
            try {
              await app.trashNode(node.id);
              ui.toast("Moved to trash");
            } catch (error) {
              ui.toast(
                error instanceof Error ? error.message : "Could not move item",
                "error",
              );
            }
          },
        });
        return;
      }

      if (mod && event.key === "ArrowUp") {
        event.preventDefault();
        void app.reorderSelected(-1);
        return;
      }
      if (mod && event.key === "ArrowDown") {
        event.preventDefault();
        void app.reorderSelected(1);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
