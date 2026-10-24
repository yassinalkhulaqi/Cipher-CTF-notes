import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useUiStore } from "../store/useUiStore";

export function ToastStack() {
  const toasts = useUiStore((state) => state.toasts);
  const dismissToast = useUiStore((state) => state.dismissToast);

  if (toasts.length === 0) return null;

  return createPortal(
    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => {
        const Icon =
          toast.tone === "success"
            ? CheckCircle2
            : toast.tone === "error"
              ? AlertTriangle
              : Info;
        return (
          <div key={toast.id} className={`toast ${toast.tone}`} role="status">
            <span className="toast-icon">
              <Icon />
            </span>
            <span className="toast-message">{toast.message}</span>
            <button
              type="button"
              className="toast-close"
              onClick={() => dismissToast(toast.id)}
              aria-label="Dismiss"
            >
              <X />
            </button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
}
