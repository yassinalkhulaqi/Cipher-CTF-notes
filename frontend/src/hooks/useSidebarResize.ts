import {
  useCallback,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useAppStore } from "../store/useAppStore";

const MIN_SIDEBAR_WIDTH = 220;
const MAX_SIDEBAR_WIDTH = 480;

/**
 * Pointer/keyboard driven resize handle for the sidebar.
 * Commits the live width without persisting during drag, persists on release.
 */
export function useSidebarResize() {
  const sidebarWidth = useAppStore((state) => state.sidebarWidth);
  const setSidebarWidth = useAppStore((state) => state.setSidebarWidth);
  const [draggingSash, setDraggingSash] = useState(false);

  const startResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = sidebarWidth;
      setDraggingSash(true);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (moveEvent: PointerEvent) => {
        const next = Math.min(
          MAX_SIDEBAR_WIDTH,
          Math.max(MIN_SIDEBAR_WIDTH, startWidth + moveEvent.clientX - startX),
        );
        setSidebarWidth(next, false);
      };
      const onUp = () => {
        setDraggingSash(false);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        setSidebarWidth(useAppStore.getState().sidebarWidth, true);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [sidebarWidth, setSidebarWidth],
  );

  const resizeKey = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setSidebarWidth(sidebarWidth - 16, true);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        setSidebarWidth(sidebarWidth + 16, true);
      } else if (event.key === "Home") {
        event.preventDefault();
        setSidebarWidth(MIN_SIDEBAR_WIDTH, true);
      } else if (event.key === "End") {
        event.preventDefault();
        setSidebarWidth(MAX_SIDEBAR_WIDTH, true);
      }
    },
    [sidebarWidth, setSidebarWidth],
  );

  return { draggingSash, startResize, resizeKey };
}
