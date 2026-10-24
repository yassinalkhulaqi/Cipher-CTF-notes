import { useMemo, useState } from "react";
import { FolderPlus } from "lucide-react";
import { collectFolders, parentForSelection } from "../../lib/tree";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function NewFolderModal() {
  const tree = useAppStore((state) => state.tree);
  const nodes = useAppStore((state) => state.nodes);
  const selectedId = useAppStore((state) => state.selectedId);
  const createFolder = useAppStore((state) => state.createFolder);
  const newFolderParent = useUiStore((state) => state.newFolderParent);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const defaultParent =
    newFolderParent === undefined
      ? parentForSelection(nodes, selectedId)
      : newFolderParent;
  const [name, setName] = useState("");
  const [parent, setParent] = useState<number | null>(defaultParent);
  const [creating, setCreating] = useState(false);
  const folders = useMemo(() => collectFolders(tree), [tree]);

  const create = async () => {
    if (!name.trim()) {
      toast("A folder needs a name", "error");
      return;
    }
    setCreating(true);
    try {
      await createFolder(name.trim(), parent);
      closeModal();
      toast(`Created “${name.trim()}”`, "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not create folder",
        "error",
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal
      title="New folder"
      subtitle="Keep the vault organized"
      icon={<FolderPlus />}
      footer={
        <>
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Cancel
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => void create()}
            disabled={creating}
          >
            <FolderPlus /> {creating ? "Creating…" : "Create folder"}
          </button>
        </>
      }
      label="New folder"
    >
      <div className="form-stack">
        <div className="field">
          <label htmlFor="new-folder-name">Folder name</label>
          <input
            id="new-folder-name"
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            placeholder="Recon"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void create();
              }
            }}
          />
        </div>
        <div className="field">
          <label htmlFor="new-folder-parent">Parent folder</label>
          <select
            id="new-folder-parent"
            className="select"
            value={parent ?? ""}
            onChange={(event) =>
              setParent(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">Vault root</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {"  ".repeat(folder.depth)}
                {folder.title}
              </option>
            ))}
          </select>
        </div>
      </div>
    </Modal>
  );
}
