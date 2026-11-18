import { useRef, useState } from "react";
import type { DragEvent } from "react";
import { FileUp, UploadCloud } from "lucide-react";
import { parseTags } from "../format";
import type { EvidenceUpload } from "../types";

interface IngestPanelProps {
  busy: boolean;
  onUpload: (upload: EvidenceUpload) => void;
  onDrag: (active: boolean) => void;
}

export function IngestPanel({ busy, onUpload, onDrag }: IngestPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [tags, setTags] = useState("");
  const [operator, setOperator] = useState("");
  const [caseReference, setCaseReference] = useState("");

  const submit = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const parsedTags = parseTags(tags);
    for (const file of Array.from(files)) {
      onUpload({
        file,
        tags: parsedTags,
        operator: operator.trim(),
        caseReference: caseReference.trim(),
      });
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    onDrag(false);
    submit(event.dataTransfer.files);
  };

  return (
    <div className="ev-ingest">
      <div
        className="ev-dropzone"
        onDragEnter={(event) => {
          event.preventDefault();
          onDrag(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => onDrag(false)}
        onDrop={handleDrop}
      >
        <UploadCloud size={26} aria-hidden="true" />
        <strong>Drop evidence files here</strong>
        <span>Files are hashed and stored with a chain-of-custody record.</span>
        <button
          type="button"
          className="ev-btn ev-btn--primary"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          <FileUp size={14} aria-hidden="true" /> Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="ev-visually-hidden"
          onChange={(event) => {
            submit(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      <div className="ev-ingest__fields">
        <label>
          <span>Tags</span>
          <input
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="web, screenshot, root-cause"
          />
        </label>
        <label>
          <span>Operator</span>
          <input
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
            placeholder="analyst name"
          />
        </label>
        <label>
          <span>Case reference</span>
          <input
            value={caseReference}
            onChange={(event) => setCaseReference(event.target.value)}
            placeholder="CASE-2026-001"
          />
        </label>
      </div>
    </div>
  );
}
