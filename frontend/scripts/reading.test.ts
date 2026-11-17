import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  DEFAULT_READING_PREFS,
  buildReadingOutline,
  formatReadingStats,
  formatReadingTime,
  normalizeReadingPrefs,
  readingExcerpt,
  readingParagraphs,
  readingStats,
} from "../src/lib/reading";

const root = process.cwd();

test("reading prefs normalize to safe defaults", () => {
  assert.deepEqual(normalizeReadingPrefs(undefined), DEFAULT_READING_PREFS);
  assert.deepEqual(normalizeReadingPrefs(null), DEFAULT_READING_PREFS);
  assert.deepEqual(normalizeReadingPrefs({}), DEFAULT_READING_PREFS);
});

test("reading prefs clamp values into range and resolve theme", () => {
  const prefs = normalizeReadingPrefs({
    fontSize: 99,
    lineLength: -5,
    leading: 9,
    theme: "graphite",
    measure: false,
  });

  assert.equal(prefs.fontSize, 28);
  assert.equal(prefs.lineLength, 40);
  assert.equal(prefs.leading, 2.2);
  assert.equal(prefs.theme, "graphite");
  assert.equal(prefs.measure, false);
});

test("reading stats derive prose metrics and reading time", () => {
  const markdown = [
    "# Recon",
    "",
    "We enumerated the host and ran nmap.",
    "",
    "The port scan finished fast.",
  ].join("\n");

  const stats = readingStats(markdown);

  assert.equal(stats.headings, 1);
  assert.equal(stats.paragraphs, 2);
  assert.ok(stats.words > 0);
  assert.ok(stats.readingSeconds >= 1);
});

test("reading outline lists headings with depth and one-based line", () => {
  const outline = buildReadingOutline("# Alpha\n\n## Beta\n\ntext\n");

  assert.equal(outline.length, 2);
  assert.equal(outline[0]?.level, 1);
  assert.equal(outline[0]?.text, "Alpha");
  assert.equal(outline[0]?.line, 1);
  assert.equal(outline[1]?.level, 2);
  assert.equal(outline[1]?.text, "Beta");
});

test("reading excerpt keeps short prose intact and truncates long prose", () => {
  assert.equal(readingExcerpt("one two three four five", 3), "one two…");
  assert.equal(readingExcerpt("one two", 5), "one two");
  assert.equal(readingExcerpt("", 5), "");
});

test("formatReadingStats composes the footer summary", () => {
  const summary = formatReadingStats(
    readingStats("# One\n\nTwo words here.\n"),
  );
  assert.equal(summary.words, 3);
  assert.equal(summary.paragraphs, 1);
  assert.equal(summary.headings, 1);
  assert.equal(summary.reading, "9s read");
});

test("readingParagraphs ignores headings and blank blocks", () => {
  const blocks = readingParagraphs(
    "# Title\n\nOne two.\n\n## Sub\n\nThree four.\n",
  );
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0], "One two.");
  assert.equal(blocks[1], "Three four.");
});

test("formatReadingTime renders minutes and seconds", () => {
  assert.equal(formatReadingTime(45), "45s read");
  assert.equal(formatReadingTime(125), "2 min 5s read");
});

test("reading styles ship theme tokens and measure controls", () => {
  const css = readFileSync(path.join(root, "src/styles/reading.css"), "utf8");
  const index = readFileSync(path.join(root, "src/styles/index.css"), "utf8");

  assert.match(css, /\.reading-view/);
  assert.match(css, /data-reading-theme="graphite"/);
  assert.match(css, /reading-progress/);
  assert.match(css, /reading-article/);
  assert.match(index, /reading\.css/);
});
