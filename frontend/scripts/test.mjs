import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { mkdir, readFile, readdir } from "node:fs/promises";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const cache = path.join(root, "node_modules", ".cache");
const suitesDir = path.join(root, "scripts", "test-suites");

const baseTests = [
  "motion.test.ts",
  "tags.test.ts",
  "tree.test.ts",
  "router.test.ts",
  "commands.test.ts",
  "apiClient.test.ts",
  "blocks.test.ts",
  "evidence.test.ts",
  "engagements.test.ts",
];

async function extraTests() {
  let entries;
  try {
    entries = await readdir(suitesDir);
  } catch {
    return [];
  }
  const extras = [];
  for (const entry of entries.sort()) {
    if (!entry.endsWith(".json")) continue;
    const text = await readFile(path.join(suitesDir, entry), "utf8");
    const names = JSON.parse(text);
    if (!Array.isArray(names)) continue;
    extras.push(
      ...names.filter(
        (name) => typeof name === "string" && name.endsWith(".test.ts"),
      ),
    );
  }
  return extras;
}

const unitTests = [...new Set([...baseTests, ...(await extraTests())])];

async function typecheck() {
  const result = spawnSync(
    process.execPath,
    [path.join(root, "node_modules", "typescript", "bin", "tsc"), "--noEmit"],
    { cwd: root, stdio: "inherit" },
  );
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

async function unit() {
  await mkdir(cache, { recursive: true });
  for (const entry of unitTests) {
    const bundle = path.join(cache, entry.replace(/\.ts$/, ".mjs"));
    await build({
      entryPoints: [path.join(root, "scripts", entry)],
      bundle: true,
      platform: "node",
      format: "esm",
      target: "node20",
      outfile: bundle,
      logLevel: "silent",
    });
    const result = spawnSync(process.execPath, ["--test", bundle], {
      cwd: root,
      stdio: "inherit",
    });
    if (result.error) throw result.error;
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
}

if (!process.env.REDSCRIBE_SKIP_TYPECHECK) await typecheck();
await unit();
