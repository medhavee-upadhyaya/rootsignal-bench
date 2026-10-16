import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("defines a reproducible Vercel build for the portfolio path", async () => {
  const [vercelText, packageText, viteConfig] = await Promise.all([
    readFile(new URL("../vercel.json", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../vite.config.ts", import.meta.url), "utf8"),
  ]);
  const vercel = JSON.parse(vercelText);
  const packageJson = JSON.parse(packageText);
  assert.equal(vercel.framework, null);
  assert.equal(vercel.installCommand, "npm ci");
  assert.equal(vercel.buildCommand, "npm run build:vercel");
  assert.equal(vercel.outputDirectory, undefined);
  assert.match(packageJson.scripts["build:vercel"], /ROOTSIGNAL_BASE_PATH=\/project\/rootsignalbench/);
  assert.match(packageJson.scripts["build:vercel"], /NITRO_PRESET=vercel vite build/);
  assert.match(viteConfig, /import \{ nitro \} from "nitro\/vite"/);
  assert.match(viteConfig, /plugins: \[vinext\(\), nitro\(\)\]/);
});
