import { Fragment } from "react";
import type { ModalName } from "../../store/useUiStore";
import { useUiStore } from "../../store/useUiStore";
import { CommandPalette } from "./CommandPalette";
import { ConfirmModal } from "./ConfirmModal";
import { DashboardModal } from "./DashboardModal";
import { GraphModal } from "./GraphModal";
import { HelpModal } from "./HelpModal";
import { ModalExitContext } from "./Modal";
import { MotionLab } from "./MotionLab";
import { NewFolderModal } from "./NewFolderModal";
import { NewNoteModal } from "./NewNoteModal";
import { PropertiesModal } from "./PropertiesModal";
import { SearchModal } from "./SearchModal";
import { SettingsModal } from "./SettingsModal";
import { SnippetFormModal } from "./SnippetFormModal";
import { SnippetsModal } from "./SnippetsModal";
import { TrashModal } from "./TrashModal";

function renderModal(name: Exclude<ModalName, null>) {
  switch (name) {
    case "palette":
      return <CommandPalette />;
    case "search":
      return <SearchModal />;
    case "snippets":
      return <SnippetsModal />;
    case "snippet-form":
      return <SnippetFormModal />;
    case "new-note":
      return <NewNoteModal />;
    case "new-folder":
      return <NewFolderModal />;
    case "properties":
      return <PropertiesModal />;
    case "trash":
      return <TrashModal />;
    case "dashboard":
      return <DashboardModal />;
    case "graph":
      return <GraphModal />;
    case "settings":
      return <SettingsModal />;
    case "motion":
      return <MotionLab />;
    case "help":
      return <HelpModal />;
    case "confirm":
      return <ConfirmModal />;
  }
}

export function ModalHost() {
  const stack = useUiStore((state) => state.modalStack);
  const closing = useUiStore((state) => state.modalClosing);

  return (
    <>
      {stack.map((name, index) =>
        name ? (
          <ModalExitContext.Provider
            key={`${name}-${index}`}
            value={closing && index === stack.length - 1}
          >
            <Fragment>{renderModal(name)}</Fragment>
          </ModalExitContext.Provider>
        ) : null,
      )}
    </>
  );
}
