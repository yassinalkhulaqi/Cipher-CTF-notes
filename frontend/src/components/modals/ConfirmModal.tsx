import { AlertTriangle } from "lucide-react";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function ConfirmModal() {
  const request = useUiStore((state) => state.confirmRequest);
  const resolveConfirm = useUiStore((state) => state.resolveConfirm);
  const closeModal = useUiStore((state) => state.closeModal);

  if (!request) return null;

  return (
    <Modal
      size="slim"
      title={request.title}
      icon={<AlertTriangle />}
      className={`confirm-modal ${request.danger ? "danger" : ""}`}
      footer={
        <>
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${request.danger ? "danger" : "primary"}`}
            onClick={resolveConfirm}
            autoFocus
          >
            {request.confirmLabel}
          </button>
        </>
      }
      label={request.title}
    >
      <p className="confirm-message">{request.message}</p>
    </Modal>
  );
}
