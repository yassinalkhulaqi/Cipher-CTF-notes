import assert from "node:assert/strict";
import test from "node:test";

import { FocusManager, FocusError } from "../src/features/commands/focus";
import {
  MacroError,
  MacroLibrary,
  MacroRecorder,
  expandMacro,
  macroStepsAsData,
} from "../src/features/commands/macros";
import {
  NavigationGraph,
  defaultNavigation,
} from "../src/features/commands/navigation";
import {
  ParseError,
  bindArguments,
  canonicalizeCommandId,
  parseCommand,
  parseSequence,
  renderCommand,
  tokenize,
} from "../src/features/commands/parse";
import {
  groupHits,
  isCommandAvailable,
  rankCommands,
  scoreCommand,
  subsequenceRatio,
} from "../src/features/commands/scoring";
import {
  clampSelection,
  flattenGroups,
  initialPaletteState,
  isCommandBarShortcut,
  paletteReducer,
} from "../src/features/commands/state";
import type {
  ArgumentSpec,
  CommandContext,
  CommandSpec,
  UsageEvent,
} from "../src/features/commands/types";
import { UsageModel } from "../src/features/commands/usage";
import {
  MemoryPanePersistence,
  WorkspaceError,
  WorkspaceModel,
  insertPane,
  leaves,
  makePane,
  resizePane,
  paths,
} from "../src/features/commands/workspace";

function arg(
  name: string,
  overrides: Partial<ArgumentSpec> = {},
): ArgumentSpec {
  return {
    name,
    arg_type: "text",
    required: false,
    default: "",
    choices: [],
    help: "",
    max_length: 240,
    ...overrides,
  };
}

function cmd(id: string, overrides: Partial<CommandSpec> = {}): CommandSpec {
  return {
    id,
    title: id.replace(".", " "),
    group: "system",
    description: "Test command",
    keywords: [],
    aliases: [],
    arguments: [],
    capability: "commands",
    status: "enabled",
    effect: "navigate",
    order: 100,
    target_kind: "",
    requires_selection: false,
    min_permission: 0,
    ...overrides,
  };
}

const CONTEXT: CommandContext = {
  pane_id: "pane:main",
  workspace_id: "main",
  entity: null,
  selection: [],
  tags: [],
  focus_active: false,
  capabilities: ["commands"],
};

test("tokenizer handles quotes, escapes, and errors", () => {
  const tokens = tokenize('title="Hello World" --flag value');
  assert.deepEqual(
    tokens.map((token) => token.value),
    ["title=Hello World", "--flag", "value"],
  );
  assert.equal(tokens[1].flag, true);
  assert.throws(() => tokenize('title="open'), ParseError);
  assert.equal(canonicalizeCommandId("/note:new"), "note.new");
  assert.equal(canonicalizeCommandId(">CREATE.NOTE"), "create.note");
  assert.throws(() => canonicalizeCommandId("a.b.c.d"), ParseError);
});

test("parse command into named, flagged, and positional arguments", () => {
  const parsed = parseCommand(
    '/create.note title="Hello World" --tags recon --pinned side',
  );
  assert.equal(parsed.command_id, "create.note");
  assert.deepEqual(parsed.named, {
    title: "Hello World",
    tags: "recon",
    pinned: "side",
  });
  assert.deepEqual(parsed.positional, []);
  assert.throws(() => parseCommand(""), ParseError);
  assert.throws(() => parseCommand("x.y --a 1 --a 2"), ParseError);
  assert.throws(() => parseCommand('x.y title="open'), ParseError);
});

test("bind arguments validates required and typed values", () => {
  const spec = cmd("create.finding", {
    aliases: ["newfinding"],
    arguments: [
      arg("title", { required: true }),
      arg("severity", {
        arg_type: "choice",
        choices: ["low", "high"],
        default: "low",
      }),
    ],
  });
  const invocation = bindArguments(
    parseCommand('newfinding "SQL injection" high'),
    spec,
  );
  assert.equal(invocation.command_id, "create.finding");
  assert.deepEqual(invocation.arguments, {
    title: "SQL injection",
    severity: "high",
  });
  assert.throws(
    () => bindArguments(parseCommand("create.finding"), spec),
    ParseError,
  );
  assert.throws(
    () => bindArguments(parseCommand("create.finding X critical"), spec),
    ParseError,
  );
  assert.throws(
    () => bindArguments(parseCommand("create.finding X --bogus 1"), spec),
    ParseError,
  );
});

test("render command round-trips through the parser", () => {
  const spec = cmd("view.split", {
    arguments: [arg("orientation"), arg("title")],
  });
  const invocation = bindArguments(
    parseCommand('/view.split --title "Side pane" --orientation horizontal'),
    spec,
  );
  const rendered = renderCommand(invocation, spec);
  assert.equal(
    rendered,
    '/view.split --orientation horizontal --title "Side pane"',
  );
  assert.deepEqual(
    bindArguments(parseCommand(rendered), spec).arguments,
    invocation.arguments,
  );
});

test("parse a numbered sequence into data steps", () => {
  const steps = parseSequence(
    "1. /navigation.goto --ref note:a\n2. - /session.start\n\n- /navigation.back",
  );
  assert.deepEqual(
    steps.map((step) => step.command_id),
    ["navigation.goto", "session.start", "navigation.back"],
  );
});

test("scoring ranks exact matches above fuzzy ones", () => {
  const note = cmd("create.note", {
    title: "New note",
    keywords: ["document"],
  });
  const goto = cmd("navigation.goto", { title: "Go to entity" });
  assert.ok(
    scoreCommand("note", note, CONTEXT).score >
      scoreCommand("note", goto, CONTEXT).score,
  );
  assert.equal(
    scoreCommand("newnote", note, CONTEXT).signals.some((signal) =>
      signal.startsWith("alias"),
    ),
    false,
  );
  assert.ok(
    scoreCommand("new note", note, CONTEXT).signals.some((s) =>
      s.startsWith("exact"),
    ),
  );
  assert.equal(scoreCommand("zzzz", note, CONTEXT).score, 0);
  assert.equal(subsequenceRatio("abc", "aXbYc"), 1);
  assert.equal(subsequenceRatio("abc", "cba"), 1 / 3);
});

test("availability checks capability, selection, and target kind", () => {
  const write = cmd("create.note", { min_permission: 1 });
  assert.ok(isCommandAvailable(write, CONTEXT));
  assert.equal(
    isCommandAvailable(write, { ...CONTEXT, capabilities: [] }),
    false,
  );
  const needsSelection = cmd("inspect.entity", { requires_selection: true });
  assert.equal(isCommandAvailable(needsSelection, CONTEXT), false);
  assert.equal(
    isCommandAvailable(needsSelection, {
      ...CONTEXT,
      selection: [{ kind: "note", value: "a", ref: "note:a" }],
    }),
    true,
  );
  const typed = cmd("findings.open", { target_kind: "finding" });
  assert.equal(isCommandAvailable(typed, CONTEXT), false);
});

test("rank and group results deterministically", () => {
  const specs = [
    cmd("view.focus", { title: "Focus pane", group: "view" }),
    cmd("session.start", {
      title: "Start focus session",
      group: "session",
      aliases: ["focus"],
    }),
    cmd("create.note", { title: "New note", group: "create" }),
  ];
  const hits = rankCommands("focus", specs, CONTEXT);
  assert.equal(hits[0].command.id, "view.focus");
  assert.deepEqual(
    hits.map((hit) => hit.command.id),
    [...hits].sort((a, b) => b.score - a.score).map((hit) => hit.command.id),
  );
  const groups = groupHits(hits);
  assert.deepEqual(
    groups.map((group) => group.group),
    ["view", "session"],
  );
  assert.throws(() => rankCommands("x", specs, CONTEXT, { limit: 0 }));
});

test("usage model records, decays, and snapshots", () => {
  let now = 100;
  const usage = new UsageModel(100, () => now);
  usage.record(
    { command_id: "a.one", arguments: {}, source: "palette", context_ref: "" },
    "pane:main",
  );
  now = 200;
  usage.record({
    command_id: "b.two",
    arguments: {},
    source: "palette",
    context_ref: "",
  });
  assert.equal(usage.count("a.one"), 1);
  assert.equal(usage.recencyScore("a.one", 100), 1);
  assert.ok(Math.abs(usage.recencyScore("a.one", 200) - 0.5) < 0.0001);
  assert.equal(usage.recent(1)[0].command_id, "b.two");
  assert.equal(usage.frequent(2)[0].command_id, "b.two");
  const snapshot = usage.snapshot();
  const restored = new UsageModel(100, () => now);
  restored.load(snapshot);
  assert.equal(restored.size(), 2);
  assert.equal(restored.prune(150), 1);
  restored.clear();
  assert.equal(restored.size(), 0);
});

test("macro recorder captures command data only", () => {
  const recorder = new MacroRecorder(() => 42);
  assert.throws(
    () =>
      recorder.capture({
        command_id: "x.y",
        arguments: {},
        source: "",
        context_ref: "",
      }),
    MacroError,
  );
  recorder.start("triage");
  recorder.capture({
    command_id: "navigation.goto",
    arguments: { ref: "{{target}}" },
    source: "palette",
    context_ref: "",
  });
  recorder.capture({
    command_id: "session.start",
    arguments: {},
    source: "palette",
    context_ref: "",
  });
  const macro = recorder.stop("macro_1");
  assert.equal(macro.created_at, 42);
  assert.deepEqual(
    macro.steps.map((step) => step.command_id),
    ["navigation.goto", "session.start"],
  );
  assert.deepEqual(macroStepsAsData(macro)[0], {
    command_id: "navigation.goto",
    arguments: '{"ref":"{{target}}"}',
  });
  const expanded = expandMacro(macro, { target: "note:alpha" });
  assert.deepEqual(expanded[0].arguments, { ref: "note:alpha" });
  assert.equal(expanded[0].source, "macro");
  assert.throws(() => expandMacro(macro, {}), MacroError);
  const library = new MacroLibrary();
  library.add(macro);
  library.load(library.all());
  assert.equal(library.findByName("triage")?.id, "macro_1");
  assert.ok(library.remove("macro_1"));
});

test("navigation graph yields breadcrumbs and rejects invalid edges", () => {
  const graph = defaultNavigation();
  assert.equal(graph.path("vault", "findings").cost, 1);
  assert.deepEqual(
    graph.breadcrumbs("findings").map((node) => node.id),
    ["vault", "findings"],
  );
  assert.throws(() => graph.addEdge("vault", "missing"), Error);
  assert.throws(() => graph.path("vault", "missing"), Error);
  assert.equal(graph.neighbors("vault", 2).length, 2);
  const custom = new NavigationGraph();
  custom.addNode({
    id: "root",
    label: "Root",
    kind: "place",
    parent: "",
    order: 0,
    entity: null,
  });
  custom.addNode({
    id: "child",
    label: "Child",
    kind: "note",
    parent: "root",
    order: 10,
    entity: null,
  });
  custom.addEdge("root", "child");
  assert.deepEqual(
    custom.subtree("root").map((node) => node.id),
    ["child"],
  );
});

test("focus manager enforces the state machine", () => {
  let now = 10;
  const manager = new FocusManager(() => now);
  assert.equal(manager.current(), null);
  manager.start("Deep work", "note:a", "pane:main");
  assert.equal(manager.restoreTarget(), "pane:main");
  assert.throws(() => manager.start("Other"), FocusError);
  assert.equal(manager.pause().status, "paused");
  assert.equal(manager.resume().status, "active");
  assert.equal(manager.interrupt().interruptions, 1);
  now = 25;
  assert.equal(manager.end().status, "ended");
  assert.equal(manager.history().length, 1);
  assert.throws(() => manager.pause(), FocusError);
  const restored = new FocusManager(() => now);
  restored.restore(manager.snapshot());
  assert.equal(restored.status().completed, 1);
});

test("workspace tree splits, resizes, closes, and persists", () => {
  let tree = insertPane(
    { pane: makePane("pane:a") },
    "pane:a",
    makePane("pane:b"),
    "horizontal",
    0.4,
  );
  assert.deepEqual(
    leaves(tree).map((pane) => pane.id),
    ["pane:a", "pane:b"],
  );
  assert.deepEqual(paths(tree)["pane:b"], [1]);
  tree = resizePane(tree, "pane:a", 0.3);
  assert.equal(tree.ratio, 0.3);
  tree = resizePane(tree, "pane:b", 0.25);
  assert.ok(Math.abs((tree.ratio ?? 0) - 0.75) < 0.0001);
  const persistence = new MemoryPanePersistence();
  const model = new WorkspaceModel(undefined, persistence);
  assert.equal(model.active().id, "pane:main");
  model.split("pane:main", "vertical", "pane:side", "Side");
  assert.equal(model.panes().length, 2);
  model.setContext("pane:side", "note:alpha");
  model.rename("pane:side", "Evidence");
  const saved = model.save();
  const reloaded = new WorkspaceModel(undefined, persistence);
  assert.equal(reloaded.load(), true);
  assert.equal(reloaded.active().context_ref, "note:alpha");
  reloaded.close("pane:side");
  assert.deepEqual(
    reloaded.panes().map((pane) => pane.id),
    ["pane:main"],
  );
  assert.throws(() => reloaded.close("pane:main"), WorkspaceError);
  assert.equal(saved.id, "main");
});

test("palette reducer walks results and restores focus", () => {
  const groups = groupHits([
    {
      command: cmd("navigation.goto", { group: "navigation", title: "Go to" }),
      score: 2,
      signals: [],
      matched_text: "go",
    },
    {
      command: cmd("create.note", { group: "create", title: "New note" }),
      score: 1,
      signals: [],
      matched_text: "note",
    },
  ]);
  let state = paletteReducer(initialPaletteState(), {
    type: "open",
    restoreFocus: "pane:main",
    groups,
  });
  assert.equal(state.open, true);
  assert.equal(flattenGroups(state.groups).length, 2);
  state = paletteReducer(state, { type: "move", delta: 1 });
  assert.equal(state.selected, 1);
  state = paletteReducer(state, { type: "move", delta: 10 });
  assert.equal(state.selected, 1);
  assert.equal(clampSelection(-4, 2), 0);
  state = paletteReducer(state, { type: "toggle-group", group: "navigation" });
  assert.ok(state.collapsed.includes("navigation"));
  state = paletteReducer(state, {
    type: "edit-arguments",
    command: cmd("create.note", {
      arguments: [arg("title", { required: true })],
    }),
  });
  assert.ok(state.pending);
  state = paletteReducer(state, {
    type: "set-argument",
    name: "title",
    value: "Demo",
  });
  assert.equal(state.draft.title, "Demo");
  state = paletteReducer(state, { type: "submit" });
  assert.equal(state.submitted?.command_id, "create.note");
  assert.deepEqual(state.submitted?.arguments, { title: "Demo" });
  assert.equal(state.open, false);
  assert.ok(isCommandBarShortcut({ ctrlKey: true, key: "K" } as KeyboardEvent));
  assert.equal(
    isCommandBarShortcut({ ctrlKey: false, key: "K" } as KeyboardEvent),
    false,
  );
});

test("usage events remain plain data", () => {
  const event: UsageEvent = {
    command_id: "x.y",
    timestamp: 1,
    pane_id: "pane:main",
    context_ref: "",
  };
  assert.deepEqual(Object.keys(event).sort(), [
    "command_id",
    "context_ref",
    "pane_id",
    "timestamp",
  ]);
});
