import { useEffect } from "react";
import { useAppStore } from "../store/useAppStore";

export function useAutosaveLifecycle(): void {
  useEffect(() => {
    const flushBeacon = () => {
      const { note, draft, dirty } = useAppStore.getState();
      if (!note || !dirty) return;
      const body = JSON.stringify({ id: note.id, content: draft });
      navigator.sendBeacon?.(
        "/api/save_content",
        new Blob([body], { type: "application/json" }),
      );
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") flushBeacon();
    };

    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      const { dirty } = useAppStore.getState();
      if (!dirty) return;
      flushBeacon();
      event.preventDefault();
      event.returnValue = "";
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, []);
}
