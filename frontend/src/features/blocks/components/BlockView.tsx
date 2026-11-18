import { memo, type KeyboardEvent } from "react";
import { type Block, type CalloutTone } from "../types";

export interface BlockViewProps {
  block: Block;
  selected: boolean;
  readOnly?: boolean;
  onChangeText: (text: string) => void;
  onFocus: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onToggleTask: (index: number) => void;
  onItemChange: (index: number, text: string) => void;
  onAddItem: () => void;
  onCellChange: (row: number, column: number, text: string) => void;
  onAddRow: () => void;
  onToneChange: (tone: CalloutTone) => void;
}

const TONES: CalloutTone[] = [
  "info",
  "warning",
  "success",
  "danger",
  "note",
  "tip",
];

function classFor(block: Block, selected: boolean): string {
  return [
    "block-view",
    `block-view--${block.type}`,
    selected ? "block-view--selected" : "",
    block.type === "callout" ? `block-view--tone-${block.tone}` : "",
  ]
    .filter(Boolean)
    .join(" ");
}

export const BlockView = memo(function BlockView({
  block,
  selected,
  readOnly = false,
  onChangeText,
  onFocus,
  onKeyDown,
  onToggleTask,
  onItemChange,
  onAddItem,
  onCellChange,
  onAddRow,
  onToneChange,
}: BlockViewProps) {
  const textField = (
    value: string,
    update: (next: string) => void,
    label: string,
  ) => (
    <textarea
      aria-label={label}
      className="block-view__input"
      rows={Math.max(1, value.split("\n").length)}
      spellCheck={block.type !== "code"}
      value={value}
      readOnly={readOnly}
      onChange={(event) => update(event.target.value)}
      onFocus={onFocus}
      onKeyDown={onKeyDown}
    />
  );

  if (block.type === "divider") {
    return (
      <div
        className={classFor(block, selected)}
        data-block-id={block.id}
        onClick={onFocus}
      >
        <hr />
      </div>
    );
  }

  if (block.type === "list") {
    return (
      <div className={classFor(block, selected)} data-block-id={block.id}>
        {block.items.map((item, index) => (
          <div className="block-view__row" key={`${block.id}-item-${index}`}>
            {block.style === "tasks" ? (
              <input
                aria-label={`Toggle task ${index + 1}`}
                checked={block.checked[index] ?? false}
                disabled={readOnly}
                type="checkbox"
                onChange={() => onToggleTask(index)}
              />
            ) : (
              <span className="block-view__marker">
                {block.style === "ordered" ? `${index + 1}.` : "•"}
              </span>
            )}
            <input
              aria-label={`List item ${index + 1}`}
              className="block-view__line"
              readOnly={readOnly}
              value={item}
              onChange={(event) => onItemChange(index, event.target.value)}
              onFocus={onFocus}
            />
          </div>
        ))}
        {!readOnly ? (
          <button className="block-view__add" type="button" onClick={onAddItem}>
            + item
          </button>
        ) : null}
      </div>
    );
  }

  if (block.type === "table") {
    return (
      <div className={classFor(block, selected)} data-block-id={block.id}>
        <table className="block-view__table">
          <thead>
            <tr>
              {block.headers.map((header, index) => (
                <th key={`${block.id}-head-${index}`}>
                  {header || `Column ${index + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={`${block.id}-row-${rowIndex}`}>
                {block.headers.map((_header, columnIndex) => (
                  <td key={`${block.id}-cell-${rowIndex}-${columnIndex}`}>
                    <input
                      aria-label={`Cell ${rowIndex + 1}, ${columnIndex + 1}`}
                      readOnly={readOnly}
                      value={row[columnIndex] ?? ""}
                      onChange={(event) =>
                        onCellChange(rowIndex, columnIndex, event.target.value)
                      }
                      onFocus={onFocus}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!readOnly ? (
          <button className="block-view__add" type="button" onClick={onAddRow}>
            + row
          </button>
        ) : null}
      </div>
    );
  }

  if (block.type === "image") {
    return (
      <figure className={classFor(block, selected)} data-block-id={block.id}>
        <div className="block-view__placeholder">Image placeholder</div>
        <input
          aria-label="Image alt text"
          placeholder="Alt text"
          readOnly={readOnly}
          value={block.alt}
          onChange={(event) => onChangeText(event.target.value)}
          onFocus={onFocus}
        />
        <input
          aria-label="Image source"
          placeholder="Source URI"
          readOnly={readOnly}
          value={block.source}
          onChange={(event) => onChangeText(event.target.value)}
          onFocus={onFocus}
        />
      </figure>
    );
  }

  if (block.type === "callout") {
    return (
      <div className={classFor(block, selected)} data-block-id={block.id}>
        <select
          aria-label="Callout tone"
          disabled={readOnly}
          value={block.tone}
          onChange={(event) => onToneChange(event.target.value as CalloutTone)}
        >
          {TONES.map((tone) => (
            <option key={tone} value={tone}>
              {tone}
            </option>
          ))}
        </select>
        {textField(block.text, onChangeText, "Callout text")}
      </div>
    );
  }

  const tag = block.type === "heading" ? `h${block.level}` : "div";
  const Content = tag as "div";
  return (
    <Content className={classFor(block, selected)} data-block-id={block.id}>
      {block.type === "quote" ? (
        <blockquote>
          {textField(block.text, onChangeText, "Quote text")}
        </blockquote>
      ) : null}
      {block.type === "code" ? (
        <div className="block-view__code">
          <span className="block-view__language">
            {block.language || "text"}
          </span>
          {textField(block.text, onChangeText, "Code text")}
        </div>
      ) : null}
      {block.type === "paragraph" || block.type === "heading"
        ? textField(block.text, onChangeText, `${block.type} text`)
        : null}
    </Content>
  );
});
