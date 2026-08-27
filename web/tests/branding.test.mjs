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
  assert.match(page, /Run \{mode === "baseline" \? "control" : "agent"\}/);
  assert.doesNotMatch(page, /DEMO DATA/);
  assert.doesNotMatch(page, /const fallback: Investigation/);
  assert.match(catalogRoute, /\/v1\/incidents/);
  assert.match(investigationRoute, /\/v1\/baselines\/deterministic/);
});

test("distinguishes oracle-backed controls from independent model runs", async () => {
  const [page, systemRoute, investigationRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/system/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/investigate/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /Oracle-backed reference/);
  assert.match(page, /Oracle hidden from agent/);
  assert.match(page, /Model endpoint is offline or not configured/);
  assert.match(page, /INCIDENTLAB_LLM_URL/);
  assert.match(systemRoute, /\/v1\/system/);
  assert.match(investigationRoute, /Execution mode must be baseline or model/);
});

test("exposes durable experiment history and run restoration", async () => {
  const [page, runsRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/runs/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /REPRODUCIBLE EXPERIMENTS/);
  assert.match(page, /loadRun\(run\.run_id\)/);
  assert.match(page, /incident hash/);
  assert.match(page, /Reproducibility manifest/);
  assert.match(page, /INCIDENT SHA-256/);
  assert.match(runsRoute, /\/v1\/runs/);
  assert.match(runsRoute, /encodeURIComponent\(runId\)/);
});
