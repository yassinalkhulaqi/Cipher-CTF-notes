import assert from "node:assert/strict";
import test from "node:test";
import {
  addTag,
  canAddTag,
  normalizeTag,
  parseTags,
  removeTag,
  serializeTags,
  TAG_MAX_COUNT,
  TAG_MAX_LENGTH,
  toggleTag,
} from "../src/lib/tags";

test("parseTags trims, drops empties and dedupes case-insensitively", () => {
  assert.deepEqual(parseTags("  ctf , HTB,, ctf ,web"), ["ctf", "HTB", "web"]);
});

test("parseTags collapses internal whitespace", () => {
  assert.deepEqual(parseTags("host   recon , web\tvhost"), [
    "host recon",
    "web vhost",
  ]);
});

test("serializeTags round-trips through parseTags", () => {
  const once = serializeTags(["b", "a", "b"]);
  assert.deepEqual(parseTags(once), ["b", "a"]);
});

test("normalizeTag strips and collapses", () => {
  assert.equal(normalizeTag("   a\tb\n c  "), "a b c");
});

test("addTag appends new tags and refuses duplicates", () => {
  assert.equal(addTag("web", "ctf"), "web, ctf");
  assert.equal(addTag("web", "WEB"), "web");
  assert.equal(addTag("", "ctf"), "ctf");
});

test("addTag enforces count and length limits", () => {
  const many = Array.from({ length: TAG_MAX_COUNT }, (_, i) => `t${i}`).join(",");
  const refused = addTag(many, "overflow");
  assert.deepEqual(parseTags(refused), parseTags(many));
  assert.equal(canAddTag(many, "overflow"), false);
  assert.equal(canAddTag("", "x".repeat(TAG_MAX_LENGTH + 1)), false);
  assert.equal(canAddTag("", "x".repeat(TAG_MAX_LENGTH)), true);
});

test("removeTag removes case-insensitively and keeps order", () => {
  assert.equal(removeTag("web, HTB, ctf", "htb"), "web, ctf");
  assert.equal(removeTag("web", "missing"), "web");
});

test("toggleTag adds and removes", () => {
  assert.equal(toggleTag("web", "ctf"), "web, ctf");
  assert.equal(toggleTag("web, ctf", "CTF"), "web");
});
