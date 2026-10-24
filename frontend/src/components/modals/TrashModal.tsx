import { useEffect, useState } from "react";
import { RotateCcw, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import type { TrashedNode } from "../../lib/types";
import { formatDate, plural } from "../../lib/utils";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function TrashModal() {
  const restoreNode = useAppStore((state) => state.restoreNode);
  const emptyTrash = useAppStore((state) => state.emptyTrash);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [items, setItems] = useState<TrashedNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    api
      .trashedNodes()
      .then((nodes) => setItems(nodes))
      .catch((error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not load trash",
          "error",
        ),
      )
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const restore = async (id: number) => {
    setBusy(id);
    try {
      await restoreNode(id);
      setItems((current) => current.filter((item) => item.id !== id));
      toast("Note restored", "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not restore note",
        "error",
      );
    } finally {
      setBusy(null);
    }
  };

  const empty = () => {
    askConfirm({
      title: "Empty trash",
      message: `Permanently delete ${plural(items.length, "item")}? This cannot be undone.`,
      confirmLabel: "Empty trash",
      danger: true,
      action: async () => {
        try {
          const removed = await emptyTrash();
          setItems([]);
          toast(`Permanently deleted ${plural(removed, "item")}`, "success");
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not empty trash",
            "error",
          );
        }
      },
    });
  };

  return (
    <Modal
      title="Trash"
      subtitle={loading ? "Loading…" : plural(items.length, "deleted item")}
      icon={<Trash2 />}
      className="trash-modal"
      footer={
        <>
          <span className="modal-hint">
            Items in the trash can be restored at any time.
          </span>
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Close
          </button>
          <button
            type="button"
            className="btn danger-ghost"
            onClick={empty}
            disabled={items.length === 0}
          >
            <Trash2 /> Empty trash
          </button>
        </>
      }
      label="Trash"
    >
      {loading ? (
        <div className="tree-skeleton">
          <span style={{ width: "74%" }} />
          <span style={{ width: "58%" }} />
          <span style={{ width: "66%" }} />
        </div>
      ) : items.length === 0 ? (
        <div className="empty">
          <Trash2 />
          <div>
            <strong>Trash is empty</strong>
            <br />
            Deleted notes will appear here so you can restore them.
          </div>
        </div>
      ) : (
        <div className="trash-list">
          {items.map((item) => (
            <div className="trash-item" key={item.id}>
              <div className="ti-copy">
                <div className="ti-title">{item.title}</div>
                <div className="ti-path">{item.path || "Vault root"}</div>
              </div>
              {item.trashed_at ? (
                <div className="ti-date">
                  {formatDate(item.trashed_at, true)}
                </div>
              ) : null}
              <button
                type="button"
                className="btn ghost tiny"
                onClick={() => void restore(item.id)}
                disabled={busy === item.id}
              >
                <RotateCcw /> {busy === item.id ? "Restoring…" : "Restore"}
              </button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
