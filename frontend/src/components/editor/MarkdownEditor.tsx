import {
  forwardRef,
  memo,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type CompositionEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  ArrowLeftRight,
  ChevronDown,
  ChevronUp,
  Search,
  X,
} from "lucide-react";
import { highlightMarkdown, type MdToken } from "../../lib/markdownHighlight";
import { escapeRegExp } from "../../lib/utils";
import { useUiStore } from "../../store/useUiStore";

export interface MarkdownEditorHandle {
  focus: () => void;
  scrollToTop: () => void;
  wrapSelection: (prefix: string, suffix: string, placeholder: string) => void;
  toggleLinePrefix: (prefix: string) => void;
  insertBlock: (block: string) => void;
  insertText: (text: string) => void;
}

interface MarkdownEditorProps {
  noteId: number;
  value: string;
  onChange: (value: string) => void;
  onScroll?: (scrollTop: number, scrollable: number) => void;
  placeholder?: string;
  ariaLabel?: string;
}

interface Match {
  start: number;
  end: number;
}

const TOKEN_CLASS: Record<MdToken["kind"], string> = {
  text: "",
  syntax: "md-syntax",
  heading: "md-heading",
  quote: "md-quote",
  code: "md-code",
  link: "md-link",
  "code-inline": "md-inline-code",
  strong: "md-strong",
  em: "md-em",
  strike: "md-strike",
  check: "md-check",
};

const HighlightLine = memo(function HighlightLine({
  line,
}: {
  line: MdToken[];
}) {
  return (
    <div className="editor-line">
      {line.map((token, index) =>
        token.kind === "text" ? (
          token.text
        ) : (
          <span key={index} className={TOKEN_CLASS[token.kind]}>
            {token.text}
          </span>
        ),
      )}
      {"\u200b"}
    </div>
  );
});

function findMatches(value: string, query: string): Match[] {
  if (!query) return [];
  const haystack = value.toLowerCase();
  const needle = query.toLowerCase();
  const matches: Match[] = [];
  let index = 0;
  while (matches.length < 800) {
    const found = haystack.indexOf(needle, index);
    if (found < 0) break;
    matches.push({ start: found, end: found + query.length });
    index = found + Math.max(1, query.length);
  }
  return matches;
}

export const MarkdownEditor = forwardRef<
  MarkdownEditorHandle,
  MarkdownEditorProps
>(function MarkdownEditor(
  { noteId, value, onChange, onScroll, placeholder, ariaLabel },
  ref,
) {
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const findInputRef = useRef<HTMLInputElement>(null);
  const findMode = useUiStore((state) => state.findMode);
  const closeFind = useUiStore((state) => state.closeFind);
  const setCursorPosition = useUiStore((state) => state.setCursorPosition);
  const [composing, setComposing] = useState(false);
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [active, setActive] = useState(0);

  const lineCount = useMemo(() => {
    let count = 1;
    for (let index = 0; index < value.length; index += 1) {
      if (value.charCodeAt(index) === 10) count += 1;
    }
    return count;
  }, [value]);

  const highlighting = value.length <= 120_000 && lineCount <= 3_000;
  const lines = useMemo(
    () => (highlighting ? highlightMarkdown(value) : []),
    [highlighting, value],
  );
  const matches = useMemo(() => findMatches(value, query), [value, query]);
  const replaceOpen = findMode === "replace";

  const selectMatch = (match: Match) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.setSelectionRange(match.start, match.end);
    const before = value.slice(0, match.start);
    const line = before.split("\n").length;
    const lineStart = before.lastIndexOf("\n") + 1;
    editor.scrollTop = Math.max(0, (line - 3) * 22);
    if (highlightRef.current) {
      highlightRef.current.scrollTop = editor.scrollTop;
    }
    setCursorPosition(line, match.start - lineStart + 1);
  };

  const goToMatch = (direction: 1 | -1) => {
    if (!matches.length) return;
    const editor = editorRef.current;
    const start = editor?.selectionStart ?? 0;
    const end = editor?.selectionEnd ?? 0;
    let next: number;
    if (direction > 0) {
      next = matches.findIndex((match) => match.start >= end);
      if (next < 0) next = 0;
    } else {
      next = -1;
      for (let index = matches.length - 1; index >= 0; index -= 1) {
        if ((matches[index]?.end ?? 0) <= start) {
          next = index;
          break;
        }
      }
      if (next < 0) next = matches.length - 1;
    }
    setActive(next);
    const match = matches[next];
    if (match) selectMatch(match);
  };

  const applyText = (next: string, start: number, end: number) => {
    onChange(next);
    window.requestAnimationFrame(() => {
      const editor = editorRef.current;
      if (!editor) return;
      editor.focus();
      editor.setSelectionRange(start, end);
      updateCursor();
    });
  };

  const replaceCurrent = () => {
    if (!matches.length) return;
    const editor = editorRef.current;
    const current =
      matches[active] ??
      matches.find(
        (match) =>
          (editor?.selectionStart ?? 0) >= match.start &&
          (editor?.selectionStart ?? 0) <= match.end,
      ) ??
      matches[0];
    if (!current) return;
    const next =
      value.slice(0, current.start) + replacement + value.slice(current.end);
    onChange(next);
    window.requestAnimationFrame(() => {
      const target = current.start + replacement.length;
      const editorEl = editorRef.current;
      if (editorEl) {
        editorEl.focus();
        editorEl.setSelectionRange(target, target);
      }
      const following = findMatches(next, query).findIndex(
        (match) => match.start >= target,
      );
      setActive(following >= 0 ? following : 0);
    });
  };

  const replaceAll = () => {
    if (!matches.length || !query) return;
    const expression = new RegExp(escapeRegExp(query), "gi");
    onChange(value.replace(expression, replacement));
    setActive(0);
    window.requestAnimationFrame(() => editorRef.current?.focus());
  };

  useEffect(() => {
    if (!findMode) return;
    const editor = editorRef.current;
    if (editor) {
      const selected = value.slice(editor.selectionStart, editor.selectionEnd);
      if (selected && !selected.includes("\n")) setQuery(selected);
    }
    const timer = window.setTimeout(() => {
      findInputRef.current?.focus();
      findInputRef.current?.select();
    }, 20);
    const currentStart = editor?.selectionStart ?? 0;
    const nextIndex = matches.findIndex((match) => match.start >= currentStart);
    setActive(nextIndex >= 0 ? nextIndex : 0);
    return () => window.clearTimeout(timer);
  }, [findMode]);

  useEffect(() => {
    if (!query) return;
    const currentStart = editorRef.current?.selectionStart ?? 0;
    const nextIndex = matches.findIndex((match) => match.start >= currentStart);
    setActive(nextIndex >= 0 ? nextIndex : 0);
  }, [query, matches]);

  useEffect(() => {
    if (!findMode) return;
    const timer = window.setTimeout(() => {
      findInputRef.current?.focus();
      findInputRef.current?.select();
    }, 30);
    return () => window.clearTimeout(timer);
  }, [findMode, replaceOpen]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.scrollTop = 0;
    if (highlightRef.current) highlightRef.current.scrollTop = 0;
    updateCursor();
  }, [noteId]);

  const updateCursor = () => {
    const editor = editorRef.current;
    if (!editor) return;
    const before = value.slice(0, editor.selectionStart);
    const line = before.split("\n").length;
    const column = editor.selectionStart - before.lastIndexOf("\n");
    setCursorPosition(line, column);
  };

  const syncScroll = () => {
    const editor = editorRef.current;
    const highlight = highlightRef.current;
    if (!editor || !highlight) return;
    highlight.scrollTop = editor.scrollTop;
    highlight.scrollLeft = editor.scrollLeft;
    updateCursor();
    onScroll?.(editor.scrollTop, editor.scrollHeight - editor.clientHeight);
  };

  const wrapSelection = (
    prefix: string,
    suffix: string,
    placeholderText: string,
  ) => {
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const selected = value.slice(start, end);
    let next: string;
    let nextStart: number;
    let nextEnd: number;
    if (selected.startsWith(prefix) && selected.endsWith(suffix)) {
      const inner = selected.slice(prefix.length, selected.length - suffix.length);
      next = value.slice(0, start) + inner + value.slice(end);
      nextStart = start;
      nextEnd = start + inner.length;
    } else {
      const inner = selected || placeholderText;
      next = value.slice(0, start) + prefix + inner + suffix + value.slice(end);
      nextStart = start + prefix.length;
      nextEnd = nextStart + inner.length;
    }
    applyText(next, nextStart, nextEnd);
  };

  const toggleLinePrefix = (prefix: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    let lineEnd = value.indexOf("\n", end);
    if (lineEnd < 0) lineEnd = value.length;
    const linesToChange = value.slice(lineStart, lineEnd).split("\n");
    const stripped = linesToChange.map((line) =>
      line.replace(/^(\s*)(#{1,6}\s+|[-+*]\s+|>\s+)/, "$1"),
    );
    const all = linesToChange.every((line) => {
      const trimmed = line.trimStart();
      if (prefix === "# ") return /^#{1,6}\s+/.test(trimmed);
      if (prefix === "> ") return trimmed.startsWith(">");
      return trimmed.startsWith(prefix.trim());
    });
    const changed = all
      ? stripped
      : linesToChange.map((line) => `${prefix}${line}`);
    const replacementText = changed.join("\n");
    const next =
      value.slice(0, lineStart) + replacementText + value.slice(lineEnd);
    applyText(next, lineStart, lineStart + replacementText.length);
  };

  const insertBlock = (block: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const before = value.slice(0, start);
    const prefix = before && !before.endsWith("\n\n") ? "\n\n" : "";
    const text = `${prefix}${block}`;
    const next = value.slice(0, start) + text + value.slice(start);
    applyText(next, start + text.length, start + text.length);
  };

  const insertText = (text: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const next = value.slice(0, start) + text + value.slice(end);
    applyText(next, start + text.length, start + text.length);
  };

  useImperativeHandle(ref, () => ({
    focus: () => editorRef.current?.focus(),
    scrollToTop: () => {
      if (editorRef.current) editorRef.current.scrollTop = 0;
      if (highlightRef.current) highlightRef.current.scrollTop = 0;
    },
    wrapSelection,
    toggleLinePrefix,
    insertBlock,
    insertText,
  }));

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const control = event.ctrlKey || event.metaKey;
    if (event.key === "Tab") {
      event.preventDefault();
      const editor = event.currentTarget;
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      if (start === end && !event.shiftKey) {
        insertText("    ");
        return;
      }
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      let lineEnd = value.indexOf("\n", end);
      if (lineEnd < 0) lineEnd = value.length;
      const selected = value.slice(lineStart, lineEnd);
      const changed = selected
        .split("\n")
        .map((line) =>
          event.shiftKey ? line.replace(/^(\t| {1,4})/, "") : `    ${line}`,
        )
        .join("\n");
      const next = value.slice(0, lineStart) + changed + value.slice(lineEnd);
      applyText(next, lineStart, lineStart + changed.length);
      return;
    }
    if (
      event.key === "Enter" &&
      !control &&
      !event.shiftKey &&
      !composing
    ) {
      const editor = event.currentTarget;
      const start = editor.selectionStart;
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      let lineEnd = value.indexOf("\n", start);
      if (lineEnd < 0) lineEnd = value.length;
      const line = value.slice(lineStart, lineEnd);
      const match = /^(\s*)([-+*] \[[ xX]\] |[-+*] |\d{1,9}[.)] )(.*)$/.exec(
        line,
      );
      if (match && (match[3] ?? "").trim()) {
        event.preventDefault();
        const marker = match[2] ?? "";
        const numbered = /^(\d{1,9})([.)] )$/.exec(marker);
        const nextMarker = numbered
          ? `${Number(numbered[1]) + 1}${numbered[2]}`
          : marker;
        const text = `\n${match[1] ?? ""}${nextMarker}`;
        const next = value.slice(0, start) + text + value.slice(start);
        applyText(next, start + text.length, start + text.length);
        return;
      }
    }
    if (findMode && event.key === "Escape") {
      event.preventDefault();
      closeFind();
      editorRef.current?.focus();
      return;
    }
    if (!control) return;
    const key = event.key.toLowerCase();
    if (key === "b") {
      event.preventDefault();
      wrapSelection("**", "**", "bold text");
    } else if (key === "i") {
      event.preventDefault();
      wrapSelection("*", "*", "italic");
    } else if (key === "k") {
      event.preventDefault();
      wrapSelection("`", "`", "code");
    } else if (event.shiftKey && key === "x") {
      event.preventDefault();
      wrapSelection("~~", "~~", "struck out");
    }
  };

  const findLayer: ReactNode = findMode ? (
    <div className="find-bar" role="search" aria-label="Find in note">
      <div className="find-row">
        <Search />
        <input
          ref={findInputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find in note"
          aria-label="Find in note"
          spellCheck={false}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              goToMatch(event.shiftKey ? -1 : 1);
            } else if (event.key === "Escape") {
              event.preventDefault();
              closeFind();
              editorRef.current?.focus();
            }
          }}
        />
        <span className="find-count" aria-live="polite">
          {query
            ? matches.length
              ? `${active + 1} / ${matches.length}`
              : "No matches"
            : ""}
        </span>
        <button
          type="button"
          className="icon-btn sm"
          onClick={() => goToMatch(-1)}
          disabled={!matches.length}
          aria-label="Previous match"
          title="Previous match"
        >
          <ChevronUp />
        </button>
        <button
          type="button"
          className="icon-btn sm"
          onClick={() => goToMatch(1)}
          disabled={!matches.length}
          aria-label="Next match"
          title="Next match"
        >
          <ChevronDown />
        </button>
        <button
          type="button"
          className={`icon-btn sm ${replaceOpen ? "active" : ""}`}
          onClick={() =>
            useUiStore
              .getState()
              .openFind(replaceOpen ? "find" : "replace")
          }
          aria-label="Toggle replace"
          title="Toggle replace"
        >
          <ArrowLeftRight />
        </button>
        <button
          type="button"
          className="icon-btn sm"
          onClick={() => {
            closeFind();
            editorRef.current?.focus();
          }}
          aria-label="Close find"
          title="Close"
        >
          <X />
        </button>
      </div>
      {replaceOpen ? (
        <div className="find-row replace-row">
          <ArrowLeftRight />
          <input
            value={replacement}
            onChange={(event) => setReplacement(event.target.value)}
            placeholder="Replace with"
            aria-label="Replace with"
            spellCheck={false}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                replaceCurrent();
              } else if (event.key === "Escape") {
                event.preventDefault();
                closeFind();
                editorRef.current?.focus();
              }
            }}
          />
          <button
            type="button"
            className="btn tiny ghost"
            onClick={replaceCurrent}
            disabled={!matches.length}
          >
            Replace
          </button>
          <button
            type="button"
            className="btn tiny ghost"
            onClick={replaceAll}
            disabled={!matches.length}
          >
            All
          </button>
        </div>
      ) : null}
    </div>
  ) : null;

  return (
    <div
      className="editor-shell"
      data-plain={highlighting ? "false" : "true"}
      data-composing={composing ? "true" : "false"}
    >
      {highlighting ? (
        <pre
          ref={highlightRef}
          className={`editor-highlight ${composing ? "is-composing" : ""}`}
          aria-hidden="true"
        >
          {lines.map((line, index) => (
            <HighlightLine key={index} line={line.tokens} />
          ))}
        </pre>
      ) : null}
      <textarea
        ref={editorRef}
        className={`editor-area ${highlighting ? "is-highlighted" : ""}`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        onScroll={syncScroll}
        onSelect={updateCursor}
        onCompositionStart={(event: CompositionEvent<HTMLTextAreaElement>) => {
          void event;
          setComposing(true);
        }}
        onCompositionEnd={() => {
          window.setTimeout(() => setComposing(false), 0);
        }}
        spellCheck={false}
        autoComplete="off"
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
      {findLayer}
    </div>
  );
});
