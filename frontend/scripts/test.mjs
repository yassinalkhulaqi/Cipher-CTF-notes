import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { mkdir, readdir } from "node:fs/promises";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const cache = path.join(root, "node_modules", ".cache");

const unitTests = (
  await readdir(path.join(root, "scripts"))
)
  .filter((name) => name.endsWith(".test.ts"))
  .sort();

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

await typecheck();
await unit();
