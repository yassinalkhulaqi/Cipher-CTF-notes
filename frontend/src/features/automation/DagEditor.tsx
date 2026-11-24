/** DAG editor with pointer-drag and keyboard connection creation. */

import { useState } from "react";
import { edgesFor, layoutDag } from "./dag";
import type { DagCompilation, StepDef } from "./types";
import { STEP_LABELS } from "./types";

export interface DagEditorProps {
  steps: StepDef[];
  dag: DagCompilation;
  selectedId: string;
  onSelect: (id: string) => void;
  onConnect: (source: string, target: string) => void;
}

export function DagEditor({ steps, dag, selectedId, onSelect, onConnect }: DagEditorProps) {
  const [dragSource, setDragSource] = useState("");
  const [armedSource, setArmedSource] = useState("");
  const layout = layoutDag(steps);
  const edges = edgesFor(steps);
  const maxColumn = Math.max(0, ...layout.map((node) => node.column));

  const finishConnection = (target: string) => {
    const source = dragSource || armedSource;
    if (source) onConnect(source, target);
    setDragSource("");
    setArmedSource("");
  };

  return (
    <div className="automation-dag" data-automation="dag-editor" data-density="compact">
      <div className="automation-dag__hint" data-automation="dag-hint">
        Drag from an output handle to an input handle, or select a source and press Enter on a
        target.
      </div>
      <div className="automation-dag__canvas" style={{ ["--dag-columns" as string]: String(maxColumn + 1) }}>
        {layout.map((node) => (
          <div
            key={node.step.id}
            className="automation-dag__node"
            data-automation="dag-node"
            data-step-id={node.step.id}
            data-selected={node.step.id === selectedId ? "true" : "false"}
            data-kind={node.step.kind}
            style={{
              gridColumn: node.column + 1,
              gridRow: node.row + 1,
            }}
          >
            <button
              type="button"
              className="automation-dag__handle automation-dag__handle--in"
              data-automation="dag-input"
              aria-label={`Connect a step into ${node.step.id}`}
              onPointerUp={() => finishConnection(node.step.id)}
              onClick={() => finishConnection(node.step.id)}
            >
              in
            </button>
            <button
              type="button"
              className="automation-dag__body"
              data-automation="dag-select"
              aria-label={`Select step ${node.step.id}`}
              aria-pressed={node.step.id === selectedId}
              onClick={() => onSelect(node.step.id)}
            >
              <span className="automation-dag__id">{node.step.id}</span>
              <strong>{node.step.title}</strong>
              <span className="automation-dag__kind">{STEP_LABELS[node.step.kind]}</span>
            </button>
            <button
              type="button"
              className="automation-dag__handle automation-dag__handle--out"
              data-automation="dag-output"
              aria-label={`Start a connection from ${node.step.id}`}
              aria-pressed={armedSource === node.step.id}
              onPointerDown={() => setDragSource(node.step.id)}
              onClick={() => {
                setDragSource("");
                setArmedSource((current) => (current === node.step.id ? "" : node.step.id));
              }}
            >
              out
            </button>
          </div>
        ))}
      </div>
      <ul className="automation-dag__edges" data-automation="dag-edges">
        {edges.map((edge) => (
          <li key={`${edge.from}-${edge.to}`} data-automation="dag-edge">
            {edge.from} <span aria-hidden="true">→</span> {edge.to}
          </li>
        ))}
      </ul>
      {!dag.ok && (
        <ul className="automation-dag__issues" data-automation="dag-issues">
          {dag.issues.map((item, index) => (
            <li key={`${item.code}-${index}`} data-code={item.code}>
              {item.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
