import { useEffect, useMemo, useRef, useState } from "react";
import { AlignJustify, Minus, Moon, Plus, Sun } from "lucide-react";
import {
  MAX_READING_FONT_SIZE,
  MIN_READING_FONT_SIZE,
  type ReadingPrefs,
  type ReadingTheme,
  buildReadingOutline,
  normalizeReadingPrefs,
  formatReadingTime,
  readingExcerpt,
  readingStats,
} from "../lib/reading";

export interface ReadingViewProps {
  html: string;
  source: string;
  prefs?: Partial<ReadingPrefs> | null;
}

const LINE_LENGTHS = [45, 55, 68, 80, 100];

export function ReadingView({ html, source, prefs }: ReadingViewProps) {
  const articleRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const initial = useMemo(() => normalizeReadingPrefs(prefs), [prefs]);
  const [fontSize, setFontSize] = useState(initial.fontSize);
  const [lineLength, setLineLength] = useState(initial.lineLength);
  const [leading, setLeading] = useState(initial.leading);
  const [theme, setTheme] = useState<ReadingTheme>(initial.theme);
  const [measure, setMeasure] = useState(initial.measure);
  const [progress, setProgress] = useState(0);

  const stats = useMemo(() => readingStats(source), [source]);
  const outline = useMemo(() => buildReadingOutline(source), [source]);
  const excerpt = useMemo(() => readingExcerpt(source), [source]);

  useEffect(() => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    const update = () => {
      const max = scroll.scrollHeight - scroll.clientHeight;
      const ratio = max > 0 ? scroll.scrollTop / max : 1;
      setProgress(Math.min(1, Math.max(0, ratio)));
    };
    update();
    scroll.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      scroll.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [html]);

  const decreaseFont = () =>
    setFontSize((value) => Math.max(MIN_READING_FONT_SIZE, value - 1));
  const increaseFont = () =>
    setFontSize((value) => Math.min(MAX_READING_FONT_SIZE, value + 1));
  const cycleLineLength = () =>
    setLineLength((value) => {
      const index = LINE_LENGTHS.indexOf(value);
      return LINE_LENGTHS[(index + 1) % LINE_LENGTHS.length];
    });
  const toggleTheme = () =>
    setTheme((value) => (value === "paper" ? "graphite" : "paper"));

  return (
    <div className="reading-view" data-reading-theme={theme}>
      <header className="reading-toolbar">
        <div className="reading-controls">
          <button
            type="button"
            className="reading-btn"
            onClick={decreaseFont}
            disabled={fontSize <= MIN_READING_FONT_SIZE}
            aria-label="Decrease reading font size"
          >
            <Minus />
          </button>
          <span className="reading-value" aria-live="polite">
            {fontSize}px
          </span>
          <button
            type="button"
            className="reading-btn"
            onClick={increaseFont}
            disabled={fontSize >= MAX_READING_FONT_SIZE}
            aria-label="Increase reading font size"
          >
            <Plus />
          </button>
          <button
            type="button"
            className="reading-btn"
            onClick={cycleLineLength}
            aria-label="Cycle reading line length"
            title="Cycle reading line length"
          >
            <AlignJustify />
          </button>
          <label className="reading-select">
            <span>Leading</span>
            <select
              className="reading-select-input"
              value={leading}
              onChange={(event) => setLeading(Number(event.target.value))}
              aria-label="Reading line leading"
            >
              {[1.4, 1.6, 1.75, 2, 2.2].map((option) => (
                <option key={option} value={option}>
                  {option.toFixed(2)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className={`reading-btn ${theme === "graphite" ? "is-active" : ""}`}
            onClick={toggleTheme}
            aria-pressed={theme === "graphite"}
            aria-label="Toggle reading theme"
          >
            {theme === "paper" ? <Moon /> : <Sun />}
          </button>
          <button
            type="button"
            className={`reading-btn ${measure ? "is-active" : ""}`}
            onClick={() => setMeasure((value) => !value)}
            aria-pressed={measure}
            aria-label="Toggle reading measure"
          >
            <AlignJustify />
          </button>
        </div>
        <span className="reading-progress" aria-hidden="true">
          <span
            className="reading-progress-bar"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </span>
      </header>
      <div
        className="reading-scroll"
        ref={scrollRef}
        onScroll={(event) => {
          const target = event.currentTarget;
          const max = target.scrollHeight - target.clientHeight;
          const ratio = max > 0 ? target.scrollTop / max : 1;
          setProgress(Math.min(1, Math.max(0, ratio)));
        }}
      >
        <article
          ref={articleRef}
          className="reading-article"
          data-reading-theme={theme}
          style={{
            fontSize: `${fontSize}px`,
            lineHeight: `${leading}`,
            maxWidth: measure ? `${lineLength}ch` : undefined,
          }}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
      <footer className="reading-footer">
        <div className="reading-footer-stats">
          <span>{stats.words} words</span>
          <span>{stats.paragraphs} paragraphs</span>
          <span>{stats.headings} headings</span>
          <span>{formatReadingTime(stats.readingSeconds)}</span>
        </div>
        {outline.length > 0 ? (
          <nav className="reading-outline" aria-label="Reading outline">
            <h2>Outline</h2>
            <ol>
              {outline.map((anchor) => (
                <li key={anchor.id} data-level={anchor.level}>
                  {anchor.text}
                </li>
              ))}
            </ol>
          </nav>
        ) : null}
        {excerpt ? <p className="reading-excerpt">{excerpt}</p> : null}
      </footer>
    </div>
  );
}
