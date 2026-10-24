import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { useUiStore } from "../../store/useUiStore";

type ModalSize = "default" | "wide" | "slim" | "palette";

interface ModalProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  label?: string;
  size?: ModalSize;
  className?: string;
  bodyClassName?: string;
  footer?: ReactNode;
  children: ReactNode;
  active?: boolean;
  hideClose?: boolean;
  onClose?: () => void;
}

const SIZE_CLASS: Record<ModalSize, string> = {
  default: "",
  wide: "wide",
  slim: "slim",
  palette: "palette",
};

export function Modal({
  title,
  subtitle,
  icon,
  label,
  size = "default",
  className = "",
  bodyClassName = "",
  footer,
  children,
  active = true,
  hideClose = false,
  onClose,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeModal = useUiStore((state) => state.closeModal);
  useFocusTrap(dialogRef, active);

  const close = onClose ?? closeModal;
  const ariaLabel = label ?? (typeof title === "string" ? title : "Dialog");

  return createPortal(
    <div
      className={`overlay ${size === "palette" ? "palette-overlay" : ""}`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className={`modal ${SIZE_CLASS[size]} ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        tabIndex={-1}
      >
        {title ? (
          <div className="modal-head">
            {icon ? <span className="modal-icon">{icon}</span> : null}
            <h2>{title}</h2>
            {subtitle ? <span className="modal-sub">{subtitle}</span> : null}
            {hideClose ? null : (
              <button
                className="icon-btn sm"
                type="button"
                onClick={close}
                aria-label="Close"
              >
                <X />
              </button>
            )}
          </div>
        ) : hideClose ? null : (
          <button
            className="icon-btn sm modal-close"
            type="button"
            onClick={close}
            aria-label="Close"
          >
            <X />
          </button>
        )}
        <div className={`modal-body ${bodyClassName}`.trim()}>{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
