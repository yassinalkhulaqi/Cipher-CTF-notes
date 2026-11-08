import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "../../lib/api";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function AttachmentModal({ nodeId }: { nodeId: number }) {
  const toast = useUiStore((state) => state.toast);
  const [attachments, setAttachments] = useState<
    Array<{
      id: number;
      filename: string;
      sha256: string;
      created_at: string;
    }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .attachment({ id: nodeId })
      .then((data: any) => {
        if (!cancelled) setAttachments(data);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load attachments");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  const download = (sha256: string) => {
    const anchor = document.createElement("a");
    anchor.href = `/api/attachment/${sha256}/download`;
    anchor.download = "";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const remove = () => {
    toast("Remove attachment coming soon", "default");
  };

  if (error) {
    return (
      <div className="attachment-modal-error" role="alert">
        <span>{error}</span>
      </div>
    );
  }

  return (
    <Modal
      title="Attachments"
      subtitle="Files attached to this note"
      icon={<X />}
      className="attachment-modal"
      bodyClassName="attachment-modal-body"
      label="Attachments"
    >
      {attachments.length === 0 ? (
        <div className="attachment-empty">
          <X /> No attachments yet.
        </div>
      ) : (
        <div className="attachment-list">
          {attachments.map((att) => (
            <div
              key={att.id}
              className="attachment-row"
              onClick={() => download(att.sha256)}
            >
              <span className="attachment-filename">{att.filename}</span>
              <button
                type="button"
                className="attachment-remove"
                onClick={(e) => {
                  e.stopPropagation();
                  remove();
                }}
              >
                <X />
              </button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}