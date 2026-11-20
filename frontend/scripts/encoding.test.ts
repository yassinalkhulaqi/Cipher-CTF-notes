import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const MOJIBAKE = "\u0622\u00B7";

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === ".cache") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...sourceFiles(full));
    } else if (/\.(tsx?|css|html|svg|json)$/.test(entry.name)) {
      found.push(full);
    }
  }
  return found;
}

test("source files have no mojibake middle-dot separators", () => {
  const offenders = sourceFiles(path.join(root, "src"))
    .filter((file) => readFileSync(file, "utf8").includes(MOJIBAKE))
    .map((file) => path.relative(root, file));
  assert.deepEqual(offenders, []);
});
