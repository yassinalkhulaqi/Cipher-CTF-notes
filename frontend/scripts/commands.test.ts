import assert from "node:assert/strict";
import test from "node:test";
import {
  CommandRegistry,
  normalizeShortcut,
  type CommandDescriptor,
} from "../src/lib/commands";

function command(
  id: string,
  title: string,
  extras: Partial<CommandDescriptor> = {},
): CommandDescriptor {
  return {
    id,
    title,
    run: () => undefined,
    ...extras,
  };
}

test("register, list, get, unregister, and size track commands", () => {
  const registry = new CommandRegistry();
  const unregister = registry.register(command("note.save", "Save note"));

  assert.equal(registry.size, 1);
  assert.deepEqual(
    registry.list().map((item) => item.id),
    ["note.save"],
  );
  assert.equal(registry.get("note.save")?.title, "Save note");
  assert.equal(registry.has("note.save"), true);

  unregister();
  assert.equal(registry.size, 0);
  assert.equal(registry.unregister("missing"), false);
});

test("duplicate ids are rejected atomically", () => {
  const registry = new CommandRegistry();
  registry.register(command("one", "One"));
  assert.throws(
    () => registry.register(command("one", "Duplicate")),
    /already registered/,
  );

  assert.throws(
    () =>
      registry.registerMany([
        command("two", "Two"),
        command("one", "Duplicate"),
      ]),
    /already registered/,
  );
  assert.equal(registry.has("two"), false);

  assert.throws(
    () =>
      registry.registerMany([
        command("three", "Three"),
        command("three", "Three again"),
      ]),
    /already registered/,
  );
});

test("search ranks stronger matches first and is stable", () => {
  const registry = new CommandRegistry();
  registry.registerMany([
    command("autosave", "Autosave vault", {
      keywords: ["save", "write"],
      group: "Editing",
    }),
    command("save-note", "Save note", {
      keywords: ["write"],
      group: "Editing",
    }),
    command("settings", "Open settings", { group: "Navigation" }),
  ]);

  const results = registry.search("save");
  assert.equal(results[0]?.id, "save-note");
  assert.equal(results[1]?.id, "autosave");

  assert.deepEqual(
    registry.search("settings").map((item) => item.id),
    ["settings"],
  );
  assert.deepEqual(
    registry.search("").map((item) => item.id),
    ["autosave", "save-note", "settings"],
  );
});

test("disabled commands are excluded from search and shortcut lookup", () => {
  const registry = new CommandRegistry();
  registry.register(
    command("secret", "Secret action", {
      enabled: false,
      shortcut: "Mod+Shift+X",
    }),
  );
  registry.register(command("visible", "Visible action"));

  assert.deepEqual(
    registry.search("secret").map((item) => item.id),
    [],
  );
  assert.equal(registry.resolveShortcut("Mod+Shift+X"), null);

  assert.equal(registry.enable("secret"), true);
  assert.equal(registry.resolveShortcut("mod + shift + x")?.id, "secret");
  assert.equal(registry.disable("secret"), true);
  assert.equal(registry.enable("missing"), false);
});

test("byGroup preserves insertion order within groups", () => {
  const registry = new CommandRegistry();
  registry.registerMany([
    command("a", "Alpha", { group: "Editing" }),
    command("b", "Beta"),
    command("c", "Gamma", { group: "Editing" }),
  ]);

  const groups = registry.byGroup();
  assert.deepEqual(
    groups.Editing.map((item) => item.id),
    ["a", "c"],
  );
  assert.deepEqual(
    groups.General.map((item) => item.id),
    ["b"],
  );
});

test("resolveShortcut normalizes spacing and case", () => {
  assert.equal(normalizeShortcut(" Mod + Shift + K "), "mod+shift+k");
  const registry = new CommandRegistry();
  registry.register(
    command("palette", "Command palette", { shortcut: "Mod+K" }),
  );
  assert.equal(registry.resolveShortcut("MOD + k")?.id, "palette");
  assert.equal(registry.resolveShortcut("Mod+P"), null);
});

test("shortcut conflicts are reported", () => {
  const registry = new CommandRegistry();
  registry.register(command("first", "First", { shortcut: "Mod+K" }));
  registry.register(command("second", "Second", { shortcut: "mod + k" }));
  registry.register(command("third", "Third", { shortcut: "Mod+P" }));

  const conflicts = registry.findConflicts();
  assert.equal(conflicts.length, 1);
  assert.deepEqual(
    conflicts[0]?.commands.map((item) => item.id),
    ["first", "second"],
  );
});

test("subscribers are notified once per mutation batch", () => {
  const registry = new CommandRegistry();
  let notifications = 0;
  const unsubscribe = registry.subscribe(() => {
    notifications += 1;
  });

  registry.registerMany([command("a", "Alpha"), command("b", "Beta")]);
  assert.equal(notifications, 1);

  registry.disable("a");
  assert.equal(notifications, 2);

  registry.unregister("missing");
  assert.equal(notifications, 2);

  registry.unregister("a");
  assert.equal(notifications, 3);

  unsubscribe();
  registry.clear();
  assert.equal(notifications, 3);
});

test("register returns an idempotent unregister function", () => {
  const registry = new CommandRegistry();
  const remove = registry.register(command("a", "Alpha"));
  remove();
  remove();
  assert.equal(registry.has("a"), false);
});
