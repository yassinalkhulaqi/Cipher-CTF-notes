import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { X } from "lucide-react";
import {
  addTag,
  parseTags,
  removeTag,
  serializeTags,
  TAG_MAX_COUNT,
  TAG_MAX_LENGTH,
} from "../lib/tags";

interface TagInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  suggestions?: string[];
  disabled?: boolean;
}

/**
 * Comma-separated tag editor: chips with one-click removal, free text, and
 * an autocomplete dropdown sourced from the vault's existing tags.
 */
export function TagInput({
  id,
  value,
  onChange,
  suggestions = [],
  disabled = false,
}: TagInputProps) {
  const inputId = useId();
  const listboxId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const selected = useMemo(() => parseTags(value), [value]);

  const filteredSuggestions = useMemo(() => {
    const needle = draft.trim().toLowerCase();
    const taken = new Set(selected.map((tag) => tag.toLowerCase()));
    return suggestions
      .filter((tag) => !taken.has(tag.toLowerCase()))
      .filter((tag) => !needle || tag.toLowerCase().includes(needle))
      .slice(0, 8);
  }, [suggestions, selected, draft]);

  useEffect(() => {
    setActive(0);
  }, [draft]);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const commitDraft = (tag: string) => {
    const next = addTag(value, tag);
    if (next !== serializeTags(selected)) onChange(next);
    setDraft("");
    setOpen(false);
  };

  const commitRaw = () => {
    const normalized = draft.trim();
    if (normalized) commitDraft(normalized);
  };

  const onInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      if (open && filteredSuggestions[active]) {
        commitDraft(filteredSuggestions[active]);
      } else {
        commitRaw();
      }
      return;
    }
    if (event.key === "Backspace" && draft === "" && selected.length > 0) {
      event.preventDefault();
      onChange(removeTag(value, selected[selected.length - 1]));
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((current) =>
        filteredSuggestions.length
          ? (current + 1) % filteredSuggestions.length
          : 0,
      );
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive((current) =>
        filteredSuggestions.length
          ? (current - 1 + filteredSuggestions.length) %
            filteredSuggestions.length
          : 0,
      );
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "Tab" && open && filteredSuggestions.length > 0) {
      event.preventDefault();
      commitDraft(filteredSuggestions[active]);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`tag-input${disabled ? " is-disabled" : ""}`}
      onClick={() => inputRef.current?.focus()}
    >
      {selected.map((tag) => (
        <span className="tag-chip" key={tag.toLowerCase()}>
          {tag}
          <button
            type="button"
            className="tag-chip-remove"
            aria-label={`Remove tag ${tag}`}
            disabled={disabled}
            onClick={() => onChange(removeTag(value, tag))}
          >
            <X />
          </button>
        </span>
      ))}
      <input
        id={id ?? inputId}
        ref={inputRef}
        className="tag-input-field"
        value={draft}
        disabled={disabled}
        placeholder={
          selected.length === 0 ? "recon, web, privescâ€¦" : ""
        }
        spellCheck={false}
        autoComplete="off"
        role="combobox"
        aria-expanded={open && filteredSuggestions.length > 0}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={
          open && filteredSuggestions.length > 0
            ? `${listboxId}-option-${active}`
            : undefined
        }
        aria-label="Add a tag"
        maxLength={TAG_MAX_LENGTH}
        onChange={(event) => {
          setDraft(event.target.value);
          setOpen(true);
        }}
        onKeyDown={onInputKeyDown}
        onBlur={commitRaw}
      />
      {open && filteredSuggestions.length > 0 ? (
        <ul
          id={listboxId}
          className="tag-suggestions"
          role="listbox"
          aria-label="Existing tags"
        >
          {filteredSuggestions.map((tag, index) => (
            <li
              key={tag}
              id={`${listboxId}-option-${index}`}
              role="option"
              aria-selected={index === active}
              className={`tag-suggestion${index === active ? " active" : ""}`}
              onMouseMove={() => setActive(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                commitDraft(tag);
              }}
            >
              {tag}
            </li>
          ))}
        </ul>
      ) : null}
      {selected.length >= TAG_MAX_COUNT ? (
        <span className="tag-input-hint">Max {TAG_MAX_COUNT} tags</span>
      ) : null}
    </div>
  );
}
