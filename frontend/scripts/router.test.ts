import assert from "node:assert/strict";
import test from "node:test";
import {
  NOT_FOUND_ROUTE,
  ROUTES,
  ROUTE_REGISTRY,
  routeByName,
  routeTitle,
} from "../src/app/routes";
import {
  buildPath,
  currentRoute,
  matchRoute,
  navigate,
  parseLocation,
  resolvePath,
} from "../src/lib/router";

test("parseLocation normalizes hashes, paths, and queries", () => {
  assert.deepEqual(parseLocation(""), {
    path: "/",
    search: "",
    hash: "#/",
    query: new URLSearchParams(),
  });
  assert.equal(parseLocation("#/notes/12?tab=preview").path, "/notes/12");
  assert.equal(
    parseLocation("#/notes/12?tab=preview").query.get("tab"),
    "preview",
  );
  assert.equal(parseLocation("#notes/12").path, "/notes/12");
  assert.equal(parseLocation("##notes/12").path, "/notes/12");
  assert.equal(parseLocation("  #/search/  ").path, "/search");
});

test("matchRoute matches static and parameterized routes", () => {
  const home = matchRoute("home", "/");
  assert.equal(home?.name, "home");
  assert.deepEqual(home?.params, {});

  const note = matchRoute("note", "/notes/42");
  assert.equal(note?.name, "note");
  assert.equal(note?.params.id, "42");
  assert.equal(note?.requiresNote, true);

  assert.equal(matchRoute("note", "/notes"), null);
  assert.equal(matchRoute("engagements", "/engagements/42"), null);
});

test("matchRoute decodes params without splitting encoded slashes", () => {
  const note = matchRoute("note", "/notes/hello%20world");
  assert.equal(note?.params.id, "hello world");

  const encodedSlash = matchRoute("note", "/notes/a%2Fb");
  assert.equal(encodedSlash?.params.id, "a/b");
});

test("matchRoute rejects malformed encodings and unknown route names", () => {
  assert.equal(matchRoute("note", "/notes/%E0%A4%A"), null);
  assert.equal(matchRoute("missing" as never, "/notes/1"), null);
});

test("buildPath encodes params and round-trips through matchRoute", () => {
  const path = buildPath("note", { id: "a b/c" });
  assert.equal(path, "/notes/a%20b%2Fc");
  const match = matchRoute("note", path);
  assert.equal(match?.params.id, "a b/c");

  assert.equal(buildPath("home"), "/");
  assert.equal(buildPath("engagements"), "/engagements");
  assert.throws(() => buildPath("note", {}), /Missing route param/);
  assert.throws(() => buildPath("not-found"), /Unknown route/);
});

test("unknown paths fall back to the not-found route", () => {
  assert.equal(resolvePath("/nope").name, "not-found");
  assert.equal(resolvePath("/notes/%E0%A4%A").name, "not-found");
  assert.equal(resolvePath("/engagements").name, "engagements");
});

test("the route registry has unique names and paths", () => {
  const names = new Set(ROUTES.map((route) => route.name));
  const paths = new Set(ROUTES.map((route) => route.path));
  assert.equal(names.size, ROUTES.length);
  assert.equal(paths.size, ROUTES.length);

  for (const route of ROUTES) {
    assert.match(route.path, /^\//);
    assert.ok(route.title.length > 0);
  }
  assert.equal(NOT_FOUND_ROUTE.path, "*");
  assert.equal(ROUTE_REGISTRY.length, ROUTES.length + 1);
});

test("route helpers resolve titles without throwing", () => {
  assert.equal(routeByName("note")?.title, "Note");
  assert.equal(routeTitle("settings"), "Settings");
  assert.equal(routeTitle(routeByName("note")), "Note");
  assert.equal(routeTitle(null), "Not found");
  assert.equal(routeTitle("missing" as never), "Not found");
});

test("currentRoute and navigate are safe without a browser window", () => {
  assert.equal(currentRoute().name, "home");
  assert.equal(navigate("note", { id: 7 }), "/notes/7");
});
