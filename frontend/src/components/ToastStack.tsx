import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { AnimatePresence } from "../motion/AnimatePresence";
import { useUiStore, type ToastItem } from "../store/useUiStore";

export function ToastStack() {
  const toasts = useUiStore((state) => state.toasts);
  const dismissToast = useUiStore((state) => state.dismissToast);

  return createPortal(
    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      <AnimatePresence
        items={toasts}
        getKey={(toast: ToastItem) => toast.id}
        exitMs={180}
      >
        {(toast, { exiting }) => {
          const Icon =
            toast.tone === "success"
              ? CheckCircle2
              : toast.tone === "error"
                ? AlertTriangle
                : Info;
          return (
            <div
              className={`toast ${toast.tone} ${exiting ? "is-exiting" : ""}`.trim()}
              role="status"
            >
              <span className="toast-icon">
                <Icon />
              </span>
              <span className="toast-message">{toast.message}</span>
              <button
                type="button"
                className="toast-close"
                onClick={() => dismissToast(toast.id)}
                aria-label="Dismiss"
                disabled={exiting}
              >
                <X />
              </button>
            </div>
          );
        }}
      </AnimatePresence>
    </div>,
    document.body,
  );
}
