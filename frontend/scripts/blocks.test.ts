import assert from "node:assert/strict";
import test from "node:test";
import {
  AutosaveCoalescer,
  BLOCK_TYPES,
  BlockEditorEngine,
  BlockSearchIndex,
  MentionIndex,
  applyPatch,
  batchToPatch,
  blockFromApi,
  blockPlainText,
  blockSignature,
  buildMentionIndex,
  buildSearchIndex,
  changeBlockType,
  coalesceBatches,
  copyDocument,
  createBlock,
  deleteEntry,
  diffDocuments,
  documentFromApi,
  documentStats,
  documentToApi,
  documentWordCount,
  duplicateBlock,
  emptyDocument,
  ensureEditableBlocks,
  extractMentions,
  filterSlashCommands,
  firstError,
  hasIssue,
  highlightText,
  insertAfter,
  insertEntry,
  isCalloutTone,
  isListStyle,
  isPatchOperation,
  mentionAutocomplete,
  mentionQueryForValue,
  mergeEntries,
  moveBlockBy,
  normalizeDocument,
  normalizeId,
  normalizeItems,
  normalizeText,
  noteDocumentId,
  noteIdFromDocument,
  patchFromApi,
  patchFromDiff,
  patchIsEmpty,
  patchToApi,
  parseBlocks,
  parseDocument,
  queryTerms,
  refreshMentions,
  renderMention,
  replaceMentionTargets,
  resolveKeyboardAction,
  selectionRange,
  selectionText,
  serializeBlock,
  serializeDocument,
  slashQueryForValue,
  tokenize,
  updateEntry,
  validateDocument,
  validationReportFromApi,
} from "../src/features/blocks";
import {
  extendSelection,
  selectionPoint,
} from "../src/features/blocks/selection";

function sampleDocument(): ReturnType<typeof emptyDocument> {
  return {
    id: "doc-test",
    title: "Block notes",
    blocks: [
      createBlock("paragraph", { id: "b1", text: "Alpha beta" }),
      createBlock("heading", { id: "b2", text: "Section", level: 2 }),
    ],
    revision: 0,
    updatedAt: "2026-01-01T00:00:00.000Z",
    tags: ["CTF", "ctf", "web"],
    metadata: { case: "demo" },
  };
}

test("all nine block types have stable defaults", () => {
  assert.equal(BLOCK_TYPES.length, 9);
  for (const type of BLOCK_TYPES) {
    const block = createBlock(type);
    assert.equal(block.type, type);
    assert.match(block.id, /^blk-/);
    assert.deepEqual(block.mentions, []);
  }
  assert.equal(createBlock("heading", { level: 99 }).level, 6);
  assert.equal(createBlock("heading", { level: -2 }).level, 1);
  assert.equal(createBlock("code", { language: "python" }).language, "python");
  assert.equal(createBlock("paragraph", { language: "python" }).language, "");
  assert.deepEqual(createBlock("image", { alt: "a" }).items, []);
});

test("copyDocument is a deep copy", () => {
  const original = sampleDocument();
  const copy = copyDocument(original);
  copy.blocks[0].text = "changed";
  copy.blocks[0].items.push("item");
  copy.tags.push("extra");
  copy.metadata.case = "other";
  assert.equal(original.blocks[0].text, "Alpha beta");
  assert.deepEqual(original.blocks[0].items, []);
  assert.deepEqual(original.tags, ["CTF", "ctf", "web"]);
  assert.equal(original.metadata.case, "demo");
});

test("block text helpers cover geometry-specific content", () => {
  const list = createBlock("list", { items: ["one", "two"] });
  const table = createBlock("table", {
    headers: ["A", "B"],
    rows: [["1", "2"]],
  });
  const image = createBlock("image", { alt: "diagram", source: "file.png" });
  assert.equal(blockPlainText(list), "one\ntwo");
  assert.equal(blockPlainText(table), "A | B\n1 | 2");
  assert.equal(blockPlainText(image), "diagram file.png");
  assert.equal(blockPlainText(createBlock("divider")), "");
  assert.equal(documentWordCount(sampleDocument()), 3);
});

test("block collection helpers preserve order and identity rules", () => {
  const document = sampleDocument();
  const inserted = insertAfter(
    document,
    "b1",
    createBlock("quote", { id: "b3", text: "Quote" }),
  );
  assert.deepEqual(
    inserted.blocks.map((block) => block.id),
    ["b1", "b3", "b2"],
  );
  const moved = moveBlockBy(inserted, "b2", -1);
  assert.deepEqual(
    moved.blocks.map((block) => block.id),
    ["b1", "b2", "b3"],
  );
  const duplicated = duplicateBlock(moved, "b1");
  assert.equal(duplicated.blocks.length, 4);
  assert.notEqual(duplicated.blocks[1].id, "b1");
  const changed = changeBlockType(moved, "b2", "code");
  assert.equal(changed.blocks[1].type, "code");
});

test("empty documents are editable and idempotent", () => {
  const empty = emptyDocument();
  assert.equal(empty.blocks.length, 1);
  assert.equal(empty.blocks[0].type, "paragraph");
  assert.equal(ensureEditableBlocks(empty), empty);
  const withoutBlocks = { ...empty, blocks: [] };
  assert.equal(ensureEditableBlocks(withoutBlocks).blocks.length, 1);
});

test("normalizeText removes control characters and excess whitespace", () => {
  assert.equal(normalizeText("  a\u0000b\r\n\n\nc  d  "), "ab\n\nc d");
  assert.equal(normalizeText("abcdef", 3), "abc");
  assert.deepEqual(normalizeItems(["a", "", "  b  ", "c"]), ["a", "b", "c"]);
});

test("normalization helpers enforce limits safely", () => {
  assert.deepEqual(normalizeItems(["a", "", "b"]), ["a", "b"]);
  assert.equal(isCalloutTone("tip"), true);
  assert.equal(isCalloutTone("unknown"), false);
  assert.equal(isListStyle("tasks"), true);
  assert.equal(isListStyle("numbered"), false);
  assert.equal(isPatchOperation("insert"), true);
  assert.equal(isPatchOperation("explode"), false);
});

test("normalizeDocument deduplicates ids and canonicalizes tags", () => {
  const document = sampleDocument();
  document.blocks[1] = createBlock("heading", { id: "b1", text: "Dup" });
  const normalized = normalizeDocument(document);
  assert.notEqual(normalized.blocks[0].id, normalized.blocks[1].id);
  assert.match(normalized.blocks[1].id, /copy$/);
  assert.deepEqual(normalized.tags, ["ctf", "web"]);
  assert.equal(normalized.title, "Block notes");
});

test("normalizeId keeps safe ids and repairs unsafe ones", () => {
  assert.equal(normalizeId("blk-1"), "blk-1");
  assert.equal(normalizeId("bad id!"), "bad-id");
  assert.match(normalizeId("!!!"), /^blk-/);
});

test("block id helpers map note documents", () => {
  assert.equal(noteDocumentId(42), "note-42");
  assert.equal(noteIdFromDocument("note-42"), 42);
  assert.equal(noteIdFromDocument("doc-42"), null);
});

test("Markdown parser handles all structural block types", () => {
  const markdown = [
    "# Title",
    "",
    "```python",
    "print(1)",
    "```",
    "",
    "- [x] done",
    "- [ ] pending",
    "",
    "| Name | Value |",
    "| --- | --- |",
    "| alpha | 1 |",
    "",
    "> [!WARNING]",
    "> careful",
    "",
    "> quote",
    "",
    "![alt](image.png)",
    "",
    "---",
  ].join("\n");
  const blocks = parseBlocks(markdown);
  assert.deepEqual(
    blocks.map((block) => block.type),
    [
      "heading",
      "code",
      "list",
      "table",
      "callout",
      "quote",
      "image",
      "divider",
    ],
  );
  assert.equal(blocks[1].language, "python");
  assert.equal(blocks[1].text, "print(1)");
  assert.deepEqual(blocks[2].checked, [true, false]);
  assert.equal(blocks[2].style, "tasks");
  assert.deepEqual(blocks[3].headers, ["Name", "Value"]);
  assert.equal(blocks[4].tone, "warning");
});

test("serializer round-trips a mixed document", () => {
  const document = sampleDocument();
  document.blocks.push(
    createBlock("code", { text: "const x = 1;", language: "js" }),
    createBlock("list", { items: ["one", "two"], style: "ordered" }),
    createBlock("table", { headers: ["A", "B"], rows: [["1", "2"]] }),
    createBlock("callout", { text: "notice", tone: "tip" }),
    createBlock("divider"),
    createBlock("image", { alt: "pic", source: "pic.png" }),
  );
  const serialized = serializeDocument(document, true);
  assert.match(serialized, /^# Block notes/);
  const reparsed = parseDocument(serialized);
  assert.equal(reparsed.blocks.length, document.blocks.length + 1);
  assert.equal(reparsed.blocks.at(-1)?.type, "image");
});

test("serializeBlock escapes paragraph markers and table pipes", () => {
  assert.equal(
    serializeBlock(createBlock("paragraph", { text: "# heading" })),
    "\\# heading",
  );
  assert.equal(serializeBlock(createBlock("divider")), "---");
  assert.equal(
    serializeBlock(
      createBlock("table", { headers: ["A|B"], rows: [["x\\y"]] }),
    ),
    "| A\\|B |\n| --- |\n| x\\\\y |",
  );
});

test("parseDocument adds a title heading when absent", () => {
  const document = parseDocument("Body text", {
    id: "doc-parse",
    title: "Title",
    tags: ["a"],
  });
  assert.equal(document.id, "doc-parse");
  assert.equal(document.title, "Title");
  assert.equal(document.blocks[0].type, "heading");
  assert.equal(document.blocks[0].text, "Title");
  assert.deepEqual(document.tags, ["a"]);
});

test("mentions are extracted with kind, target, and offsets", () => {
  const text = "See @[Alpha](note:alpha-1) and @[Beta](finding:beta) now";
  const mentions = extractMentions(text, "b1");
  assert.equal(mentions.length, 2);
  assert.equal(mentions[0].kind, "note");
  assert.equal(mentions[0].target, "alpha-1");
  assert.equal(mentions[0].blockId, "b1");
  assert.equal(
    text.slice(mentions[0].start, mentions[0].end),
    "@[Alpha](note:alpha-1)",
  );
  assert.equal(extractMentions("@[x](alien:y)").length, 0);
});

test("refreshMentions and mention index support autocomplete", () => {
  const block = refreshMentions(
    createBlock("paragraph", {
      id: "b1",
      text: "@[Alpha](note:alpha) @[Beta](user:beta)",
    }),
  );
  assert.equal(block.mentions.length, 2);
  const index = buildMentionIndex([block]);
  assert.equal(index.size, 2);
  assert.deepEqual(index.targets(), ["alpha", "beta"]);
  assert.deepEqual(
    index.forTarget("alpha").map((hit) => hit.blockId),
    ["b1"],
  );
  assert.equal(mentionAutocomplete("bet", [block])[0]?.target, "beta");
});

test("mention index removes owners without dropping shared targets", () => {
  const first = refreshMentions(
    createBlock("paragraph", { id: "a", text: "@[A](note:shared)" }),
  );
  const second = refreshMentions(
    createBlock("paragraph", { id: "b", text: "@[B](note:shared)" }),
  );
  const index = new MentionIndex();
  index.add(first.id, first.mentions);
  index.add(second.id, second.mentions);
  assert.equal(index.size, 1);
  assert.equal(index.remove("a"), 0);
  assert.equal(index.forTarget("shared").length, 1);
  assert.equal(index.remove("b"), 1);
  assert.equal(index.size, 0);
});

test("mention tokens render and replace targets", () => {
  assert.equal(
    renderMention("target", "example.com", "Host"),
    "@[Host](target:example.com)",
  );
  const text = "@[Host](target:old.example) and @[Host](target:other)";
  assert.equal(
    replaceMentionTargets(text, { "target:old.example": "new.example" }),
    "@[Host](target:new.example) and @[Host](target:other)",
  );
});

test("diffDocuments reports additions and removals", () => {
  const left = sampleDocument();
  const right = {
    ...left,
    blocks: [...left.blocks, createBlock("quote", { id: "b3", text: "New" })],
  };
  const added = diffDocuments(left, right);
  assert.equal(added.entries.length, 1);
  assert.equal(added.entries[0].operation, "add");
  assert.equal(added.entries[0].blockId, "b3");
  const removed = diffDocuments(right, left);
  assert.equal(removed.entries[0].operation, "remove");
  assert.equal(removed.entries[0].blockId, "b3");
});

test("patchFromDiff and applyPatch reproduce the target document", () => {
  const left = sampleDocument();
  const right = {
    ...left,
    blocks: [
      createBlock("paragraph", { id: "b1", text: "Alpha changed" }),
      left.blocks[1],
      createBlock("code", { id: "b3", text: "x", language: "ts" }),
    ],
  };
  const patch = patchFromDiff(left, right);
  assert.equal(patch.baseRevision, 0);
  assert.equal(patch.label, "diff");
  const applied = applyPatch(left, patch);
  assert.deepEqual(
    applied.blocks.map((block) => block.id),
    ["b1", "b2", "b3"],
  );
  assert.equal(applied.blocks[0].text, "Alpha changed");
  assert.equal(applied.revision, 1);
});

test("applyPatch rejects stale revisions and foreign documents", () => {
  const document = sampleDocument();
  const stale = { ...patchFromDiff(document, document), baseRevision: 9 };
  assert.throws(() => applyPatch(document, stale), /Revision conflict/);
  const foreign = {
    ...patchFromDiff(document, document),
    documentId: "doc-other",
  };
  assert.throws(() => applyPatch(document, foreign), /different document/);
});

test("patch helpers report empty patches and touched blocks", () => {
  const document = sampleDocument();
  const empty = patchFromDiff(document, document);
  assert.equal(patchIsEmpty(empty), true);
  const patch = patchFromDiff(document, {
    ...document,
    blocks: [document.blocks[0], createBlock("quote", { id: "b9", text: "q" })],
  });
  assert.equal(patchIsEmpty(patch), false);
});

test("mergeEntries coalesces repeated updates", () => {
  const first = updateEntry(
    createBlock("paragraph", { id: "b1", text: "one" }),
    0,
  );
  const second = updateEntry(
    createBlock("paragraph", { id: "b1", text: "two" }),
    0,
  );
  const merged = mergeEntries([first, second]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].block?.text, "two");
  assert.equal(
    mergeEntries([first, deleteEntry("b1", 0)]).at(-1)?.operation,
    "delete",
  );
  const replaced = mergeEntries([
    insertEntry(createBlock("paragraph", { id: "b2" }), 1),
    updateEntry(createBlock("paragraph", { id: "b2", text: "x" }), 1),
  ]);
  assert.equal(replaced.length, 1);
  assert.equal(replaced[0].operation, "insert");
  assert.equal(replaced[0].block?.text, "x");
});

test("autosave coalescer tracks due work with an injected clock", () => {
  let now = 0;
  const coalescer = new AutosaveCoalescer(100, 300, () => now);
  const document = sampleDocument();
  const patch = patchFromDiff(document, {
    ...document,
    blocks: [
      createBlock("paragraph", { id: "b1", text: "next" }),
      document.blocks[1],
    ],
  });
  assert.equal(
    coalescer.record(document, patch.entries, { label: "typing" }),
    null,
  );
  assert.equal(coalescer.pending.length, 1);
  assert.equal(coalescer.hasPending(document.id), true);
  assert.equal(coalescer.due(50).length, 0);
  assert.equal(coalescer.due(100).length, 1);
  const flushed = coalescer.flush(100);
  assert.equal(flushed.length, 1);
  assert.equal(flushed[0].label, "typing");
  assert.equal(flushed[0].entries.length, 1);
  assert.equal(flushed[0].entries[0].operation, "update");
  assert.equal(coalescer.hasPending(), false);
});

test("autosave acknowledge and cancel manage individual documents", () => {
  const coalescer = new AutosaveCoalescer(1000, 5000, () => 0);
  const document = sampleDocument();
  coalescer.record(document, [updateEntry(document.blocks[0], 0)]);
  assert.equal(coalescer.acknowledge(document.id, 0), true);
  assert.equal(coalescer.hasPending(), false);
  coalescer.record(document, [updateEntry(document.blocks[0], 0)]);
  assert.equal(coalescer.cancel(document.id), true);
  assert.equal(coalescer.cancel(document.id), false);
});

test("coalesceBatches merges batches for the same document", () => {
  const document = sampleDocument();
  const batch = {
    documentId: document.id,
    baseRevision: 0,
    entries: [updateEntry(document.blocks[0], 0)],
    mergedFrom: 1,
    firstAtMs: 0,
    lastAtMs: 0,
    token: "",
    label: "a",
  };
  const merged = coalesceBatches([
    batch,
    { ...batch, label: "b", firstAtMs: 10, lastAtMs: 10 },
  ]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].mergedFrom, 2);
  assert.equal(merged[0].label, "b");
  const patch = batchToPatch(merged[0]);
  assert.equal(patch.documentId, document.id);
});

test("search index matches all terms and filters by type", () => {
  const first = sampleDocument();
  const second = {
    ...sampleDocument(),
    id: "doc-two",
    blocks: [createBlock("quote", { id: "q1", text: "alpha only" })],
  };
  const index = buildSearchIndex([first, second]);
  assert.equal(index.size, 3);
  const hits = index.search("alpha beta");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].documentId, first.id);
  assert.deepEqual(hits[0].highlights, ["alpha", "beta"]);
  assert.equal(
    index.search("alpha", { blockTypes: ["quote"] })[0]?.documentId,
    second.id,
  );
  assert.equal(index.search("alpha", { matchAll: false }).length, 2);
  assert.deepEqual(index.documentIds, ["doc-test", "doc-two"]);
});

test("tokenization, snippets, and highlighting are deterministic", () => {
  assert.deepEqual(tokenize("Alpha, beta! ALPHA"), ["alpha", "beta", "alpha"]);
  assert.deepEqual(queryTerms("alpha beta alpha"), ["alpha", "beta"]);
  const text = `${"x".repeat(300)} alpha`;
  const snippet = buildSearchIndex([
    {
      ...sampleDocument(),
      blocks: [createBlock("paragraph", { id: "long", text })],
    },
  ]).search("alpha")[0]?.snippet;
  assert.ok(snippet?.includes("alpha"));
  assert.equal(
    highlightText("Alpha alpha", ["alpha"]),
    "<mark>Alpha</mark> <mark>alpha</mark>",
  );
});

test("validation reports structural and safety errors", () => {
  const document = sampleDocument();
  document.blocks = [
    createBlock("image", { id: "img", source: "javascript:alert(1)", alt: "" }),
    createBlock("heading", { id: "img", text: "" }),
  ];
  const report = validateDocument(document);
  assert.equal(report.ok, false);
  assert.equal(hasIssue(report, "unsafe_source"), true);
  assert.equal(hasIssue(report, "duplicate_block_id"), true);
  assert.equal(firstError(report)?.code, "unsafe_source");
  assert.equal(documentStats(sampleDocument()).headings, 1);
});

test("valid documents produce a clean report", () => {
  const report = validateDocument(sampleDocument());
  assert.equal(report.ok, true);
  assert.equal(report.errors, 0);
  assert.equal(report.warnings, 0);
});

test("selection helpers read and clamp text ranges", () => {
  const document = sampleDocument();
  const start = selectionPoint("b1", 1);
  const range = extendSelection(selectionRange(start), "b1", 5);
  assert.equal(selectionText(document, range), "lpha");
  assert.equal(selectionText(document, selectionRange(start)), "");
  assert.deepEqual(range.anchor, start);
});

test("keyboard resolver handles editing, menus, and formatting", () => {
  assert.equal(
    resolveKeyboardAction({
      key: "Enter",
      selectionStart: 5,
      selectionEnd: 5,
      value: "hello",
    }).kind,
    "split",
  );
  assert.equal(
    resolveKeyboardAction({
      key: "Backspace",
      selectionStart: 0,
      selectionEnd: 0,
    }).kind,
    "merge",
  );
  assert.equal(
    resolveKeyboardAction({ key: "ArrowUp", selectionStart: 0 }).kind,
    "move-up",
  );
  assert.equal(
    resolveKeyboardAction({
      key: "ArrowDown",
      selectionStart: 5,
      selectionEnd: 5,
      value: "hello",
    }).kind,
    "move-down",
  );
  assert.equal(resolveKeyboardAction({ key: "z", ctrlKey: true }).kind, "undo");
  assert.equal(
    resolveKeyboardAction({ key: "Z", metaKey: true, shiftKey: true }).kind,
    "redo",
  );
  assert.deepEqual(resolveKeyboardAction({ key: "b", ctrlKey: true }), {
    kind: "format",
    payload: "bold",
  });
  assert.equal(
    resolveKeyboardAction({ key: "d", metaKey: true }).kind,
    "duplicate",
  );
  assert.equal(resolveKeyboardAction({ key: "/" }).kind, "open-slash");
  assert.deepEqual(resolveKeyboardAction({ key: "@" }), {
    kind: "format",
    payload: "mention",
  });
  assert.equal(
    resolveKeyboardAction({ key: "Enter", slashOpen: true }).kind,
    "accept-slash",
  );
  assert.equal(
    resolveKeyboardAction({ key: "Enter", mentionOpen: true }).kind,
    "accept-mention",
  );
  assert.equal(
    resolveKeyboardAction({ key: "Escape", slashOpen: true }).kind,
    "close-slash",
  );
  assert.equal(resolveKeyboardAction({ key: "Tab" }).kind, "indent");
  assert.equal(
    resolveKeyboardAction({ key: "Tab", shiftKey: true }).kind,
    "outdent",
  );
  assert.equal(resolveKeyboardAction({ key: "q" }).kind, "none");
});

test("slash and mention query helpers operate on caret text", () => {
  assert.equal(slashQueryForValue("type /head now", 10), "head");
  assert.equal(slashQueryForValue("plain", 5), null);
  assert.equal(mentionQueryForValue("hi @ali", 7), "ali");
  assert.equal(mentionQueryForValue("email@x", 7), null);
});

test("slash commands rank by title, type, and keywords", () => {
  assert.equal(filterSlashCommands("head")[0]?.blockType, "heading");
  assert.equal(filterSlashCommands("todo")[0]?.blockType, "list");
  assert.equal(filterSlashCommands("zzzz").length, 0);
  assert.equal(filterSlashCommands("", 3).length, 3);
});

test("API conversion preserves snake_case transport fields", () => {
  const document = sampleDocument();
  const api = documentToApi(document);
  assert.equal(api.updated_at, document.updatedAt);
  const restored = documentFromApi(api);
  assert.deepEqual(restored, document);
  const block = blockFromApi({
    id: "b1",
    type: "heading",
    level: 9,
    mentions: [],
    attrs: {},
  });
  assert.equal(block.type, "heading");
  assert.equal(block.level, 9);
  assert.equal(blockFromApi({ type: "mystery" }).type, "paragraph");
});

test("API patch conversion round-trips operations", () => {
  const patch = patchFromDiff(sampleDocument(), {
    ...sampleDocument(),
    blocks: [createBlock("paragraph", { id: "b1", text: "changed" })],
  });
  const api = patchToApi(patch);
  assert.equal(api.base_revision, 0);
  assert.equal(Array.isArray(api.entries), true);
  const restored = patchFromApi(api);
  assert.equal(restored.documentId, patch.documentId);
  assert.equal(restored.baseRevision, patch.baseRevision);
  assert.equal(restored.label, patch.label);
  assert.deepEqual(
    restored.entries.map((entry) => [
      entry.operation,
      entry.blockId,
      entry.index ?? null,
      entry.previousIndex ?? null,
    ]),
    patch.entries.map((entry) => [
      entry.operation,
      entry.blockId,
      entry.index ?? null,
      entry.previousIndex ?? null,
    ]),
  );
});

test("API report conversion tolerates partial payloads", () => {
  const report = validationReportFromApi({
    target: "doc",
    ok: false,
    errors: 1,
    warnings: 2,
    issues: [
      { severity: "error", code: "bad", message: "Bad", block_id: "b1" },
    ],
  });
  assert.equal(report.ok, false);
  assert.equal(report.issues[0].blockId, "b1");
  assert.equal(report.issues[0].field, "");
  const clean = validationReportFromApi({ target: "doc" });
  assert.equal(clean.ok, true);
  assert.equal(clean.issues.length, 0);
});

test("editor engine inserts, splits, merges, undoes, and redoes", () => {
  const engine = BlockEditorEngine.fromDocument(sampleDocument());
  engine.insert("code", "b1");
  assert.equal(engine.document.blocks[1].type, "code");
  assert.equal(engine.canUndo, true);
  engine.undo();
  assert.equal(engine.document.blocks.length, 2);
  engine.redo();
  assert.equal(engine.document.blocks.length, 3);
  assert.equal(engine.canRedo, false);

  const splitter = BlockEditorEngine.fromDocument(sampleDocument());
  splitter.split("b1", 3);
  assert.equal(splitter.document.blocks[0].text, "Alp");
  assert.equal(splitter.document.blocks[1].text, "ha beta");
  splitter.merge(splitter.document.blocks[1].id);
  assert.equal(splitter.document.blocks[0].text, "Alpha beta");
});

test("editor engine applies text, formats, and slash commands", () => {
  const engine = BlockEditorEngine.fromDocument(sampleDocument());
  engine.setText("b1", "  spaced  ");
  assert.equal(engine.document.blocks[0].text, "spaced");
  engine.applyFormat("b1", "bold");
  assert.equal(engine.document.blocks[0].text, "**spaced**");
  engine.setText("b1", "/head instruction");
  engine.acceptSlash("heading", "b1");
  assert.equal(engine.document.blocks[0].type, "heading");
  assert.equal(engine.document.blocks[0].text, "instruction");
});

test("editor engine tracks patches and remote documents", () => {
  const original = sampleDocument();
  const engine = BlockEditorEngine.fromDocument(original);
  engine.setText("b1", "Server note");
  const patch = engine.patchSince(original);
  assert.equal(patch.entries.length, 1);
  assert.equal(patch.documentId, original.id);
  const remote = { ...original, title: "From server", revision: 7 };
  engine.applyRemoteDocument(remote);
  assert.equal(engine.document.title, "From server");
  assert.equal(engine.document.revision, 7);
  assert.equal(engine.snapshot.selection.anchor.blockId, "b1");
});

test("editor engine rejects invalid merges and no-op changes safely", () => {
  const engine = BlockEditorEngine.fromDocument(sampleDocument());
  assert.equal(engine.merge("b1"), null);
  engine.toggleTask("b1", 0);
  assert.equal(engine.document.blocks[0].type, "paragraph");
  engine.addRow("b1");
  engine.addColumn("b1");
  assert.equal(engine.document.blocks[0].rows.length, 0);
  assert.equal(engine.document.blocks[0].headers.length, 0);
  assert.equal(engine.wordCount(), 3);
});

test("block signatures ignore ids and mention offsets", () => {
  const left = createBlock("paragraph", { id: "a", text: "same" });
  const right = createBlock("paragraph", { id: "b", text: "same" });
  assert.equal(blockSignature(left), blockSignature(right));
  right.text = "different";
  assert.notEqual(blockSignature(left), blockSignature(right));
});

test("search index replacement removes stale postings", () => {
  const index = new BlockSearchIndex();
  const document = sampleDocument();
  index.add(document);
  assert.equal(index.search("beta").length, 1);
  index.replace({
    ...document,
    blocks: [createBlock("paragraph", { id: "b1", text: "gamma" })],
  });
  assert.equal(index.search("beta").length, 0);
  assert.equal(index.search("gamma").length, 1);
  assert.equal(index.remove(document.id), true);
  assert.equal(index.size, 0);
});
