import assert from "node:assert/strict";
import test from "node:test";

import {
  initialShellState,
  reduceShell,
  shortcutMap,
} from "../src/features/v4-kernel/shell";
import {
  routeByPath,
  routeByName,
  V4_ROUTES,
} from "../src/features/v4-kernel/routes";
import { V4ApiError, V4Client } from "../src/features/v4-kernel/client";
import type { V4Envelope, V4Error } from "../src/features/v4-kernel/types-v4";

test("v4 routes are unique and ordered", () => {
  const names = V4_ROUTES.map((route) => route.name);
  assert.equal(new Set(names).size, names.length);
  assert.equal(V4_ROUTES.length, 10);
  assert.equal(V4_ROUTES[0].name, "inbox");
  assert.equal(V4_ROUTES[9].name, "a11y-i18n");
});

test("route lookup by name and path", () => {
  assert.equal(routeByName("findings")?.label, "Findings");
  assert.equal(routeByPath("/v4/graph/")?.name, "graph-workbench");
  assert.equal(routeByPath("/missing"), undefined);
});

test("shell reducer handles navigation and preferences", () => {
  let state = initialShellState();
  assert.equal(state.active, "inbox");
  state = reduceShell(state, { type: "navigate", name: "query" });
  assert.equal(state.active, "query");
  state = reduceShell(state, { type: "toggle-sidebar" });
  assert.equal(state.sidebarOpen, false);
  state = reduceShell(state, { type: "set-theme", theme: "graphite" });
  state = reduceShell(state, { type: "set-density", density: "compact" });
  state = reduceShell(state, { type: "set-motion", motion: "off" });
  state = reduceShell(state, {
    type: "set-locale",
    locale: "ar",
    direction: "rtl",
  });
  assert.equal(state.preference.theme, "graphite");
  assert.equal(state.preference.density, "compact");
  assert.equal(state.preference.motion, "off");
  assert.equal(state.preference.direction, "rtl");
});

test("shortcut map has all ten routes", () => {
  assert.equal(Object.keys(shortcutMap()).length, 10);
  assert.equal(shortcutMap()["Ctrl+Shift+G"], "graph-workbench");
});

test("client decodes a success envelope", async () => {
  const response = {
    ok: true,
    status: 200,
    json: async () =>
      ({
        data: { id: "x" },
        meta: { request_id: "r", version: "v4", page: 1, page_size: 50 },
      }) satisfies V4Envelope<{ id: string }>,
  } as Response;
  const client = new V4Client(
    "/api/v4",
    (async () => response) as typeof fetch,
  );
  const result = await client.get<{ id: string }>("/inbox");
  assert.equal(result.data.id, "x");
  assert.equal(result.meta.version, "v4");
});

test("client throws a structured V4ApiError", async () => {
  const response = {
    ok: false,
    status: 404,
    json: async () =>
      ({
        error: { code: "not_found", message: "missing", details: ["id"] },
      }) satisfies V4Error,
  } as Response;
  const client = new V4Client(
    "/api/v4",
    (async () => response) as typeof fetch,
  );
  await assert.rejects(
    () => client.get("/missing"),
    (error: unknown) =>
      error instanceof V4ApiError && error.code === "not_found",
  );
});
