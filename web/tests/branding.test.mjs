import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("uses the RootSignal product identity", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /RootSignal/);
  assert.match(page, /RootSignal Bench/);
  assert.match(layout, /RootSignal/);
  assert.match(packageJson, /rootsignal-web/);
});

test("implements a selectable incident workflow without fabricated results", async () => {
  const [page, catalogRoute, investigationRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/incidents/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/investigate/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /selectedIncidentId/);
  assert.match(page, /Benchmark incident/);
  assert.match(page, /Run baseline/);
  assert.doesNotMatch(page, /DEMO DATA/);
  assert.doesNotMatch(page, /const fallback: Investigation/);
  assert.match(catalogRoute, /\/v1\/incidents/);
  assert.match(investigationRoute, /\/v1\/baselines\/deterministic/);
});
