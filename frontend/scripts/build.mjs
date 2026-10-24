import { context } from "esbuild";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { watch } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.resolve(root, "../src/redscribe/ui/web/static");
const assetsDir = path.join(outDir, "assets");
const watchMode = process.argv.includes("--watch");

const options = {
  entryPoints: [path.join(root, "src/main.tsx")],
  bundle: true,
  splitting: false,
  minify: !watchMode,
  sourcemap: watchMode ? "inline" : false,
  outdir: assetsDir,
  entryNames: "app",
  assetNames: "[name]-[hash]",
  format: "esm",
  target: ["es2020"],
  jsx: "automatic",
  define: {
    "process.env.NODE_ENV": watchMode ? '"development"' : '"production"',
  },
  loader: {
    ".svg": "file",
    ".png": "file",
    ".woff2": "file",
  },
  legalComments: "none",
  logLevel: "info",
};

async function copyStatic() {
  await mkdir(assetsDir, { recursive: true });
  for (const name of ["favicon.svg", "manifest.webmanifest"]) {
    await cp(path.join(root, "public", name), path.join(outDir, name));
  }
  const html = await readFile(path.join(root, "index.html"), "utf8");
  await writeFile(path.join(outDir, "index.html"), html, "utf8");
}

async function run() {
  if (!watchMode) {
    await rm(outDir, { recursive: true, force: true });
  }
  await copyStatic();

  const ctx = await context(options);
  if (watchMode) {
    await ctx.watch();
    console.log(`[redscribe] watching ${path.relative(root, outDir)}`);
    watch(path.join(root, "public"), { persistent: true }, () => {
      copyStatic().catch((error) => console.error("[redscribe] copy failed", error));
    });
    watch(path.join(root, "index.html"), { persistent: true }, () => {
      copyStatic().catch((error) => console.error("[redscribe] copy failed", error));
    });
  } else {
    await ctx.rebuild();
    await ctx.dispose();
    console.log(`[redscribe] built ${path.relative(root, outDir)}`);
  }
}

run().catch((error) => {
  console.error("[redscribe] build failed", error);
  process.exitCode = 1;
});
