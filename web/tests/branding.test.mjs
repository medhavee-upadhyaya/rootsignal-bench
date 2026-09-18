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
  assert.match(page, /system\?\.llm\.message/);
  assert.match(page, /model_not_loaded/);
  assert.match(page, /INCIDENTLAB_LLM_URL/);
  assert.match(page, /LOCAL MODEL SETUP/);
  assert.match(page, /ollama serve/);
  assert.match(page, /Verify connection/);
  assert.match(page, /No browser API key/);
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
  assert.match(page, /Load more experiments/);
  assert.match(page, /historyCursor/);
  assert.match(page, /incident hash/);
  assert.match(page, /Reproducibility manifest/);
  assert.match(page, /INCIDENT SHA-256/);
  assert.match(runsRoute, /\/v1\/runs/);
  assert.match(runsRoute, /encodeURIComponent\(runId\)/);
  assert.match(runsRoute, /encodeURIComponent\(cursor\)/);
});

test("supports fixture-matched regression comparisons", async () => {
  const [page, compareRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/compare/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /REGRESSION ANALYSIS/);
  assert.match(page, /same incident and fixture revision/);
  assert.match(page, /findControlAgentPair/);
  assert.match(page, /CANDIDATE VERDICT/);
  assert.match(page, /comparison\.deltas\.latency_ms/);
  assert.match(page, /EXPERIMENT INPUTS/);
  assert.match(page, /Interpret the verdict with caution/);
  assert.match(page, /Copy review link/);
  assert.match(page, /parseReviewLink/);
  assert.match(compareRoute, /\/v1\/comparisons/);
});

test("supports guided and validated JSON incident imports", async () => {
  const [page, catalogRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/incidents/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /Investigate a real incident/);
  assert.match(page, /Guided builder/);
  assert.match(page, /JSON import/);
  assert.match(page, /HIDDEN ROOT CAUSE/);
  assert.match(page, /buildFixture/);
  assert.match(catalogRoute, /export async function POST/);
  assert.match(catalogRoute, /\/v1\/incidents/);
});

test("separates real incident response from oracle-backed evaluation", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /Live investigation/);
  assert.match(page, /No answer key · ungraded/);
  assert.match(page, /RUNBOOK · OPTIONAL FOR LIVE INCIDENTS/);
  assert.match(page, /draft\.runbook\.trim\(\) \?/);
  assert.match(page, /creatorPurpose === "evaluation"/);
  assert.match(page, /selectedIncident\?\.metadata\.evaluable === false/);
  assert.match(page, /run\.mode === "model" && run\.evaluable/);
});

test("lets users define a safe per-run investigation question", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /INVESTIGATION QUESTION/);
  assert.match(page, /onChange=\{\(event\) => setQuery\(event\.target\.value\)\}/);
  assert.match(page, /Reset to incident summary/);
  assert.match(page, /credentials rejected before execution/);
  assert.doesNotMatch(page, /aria-label="Incident description"[\s\S]{0,80}readOnly/);
});

test("imports a local telemetry bundle into the incident builder", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /IMPORT TELEMETRY BUNDLE · JSON/);
  assert.match(page, /parseTelemetryBundle\(await file\.text\(\)\)/);
  assert.match(page, /Parsed in your browser/);
  assert.match(page, /review every field before saving/);
});

test("archives custom incidents with explicit confirmation", async () => {
  const [page, route] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/incidents/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(page, /Confirm archive/);
  assert.match(page, /archiveSelectedIncident/);
  assert.match(page, /catalog_source === "custom"/);
  assert.match(route, /export async function DELETE/);
  assert.match(route, /encodeURIComponent\(incidentId\)/);
});

test("shows evidence sufficiency instead of trusting model confidence", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /grounding\?: \{ status: "grounded" \| "limited" \| "insufficient"/);
  assert.match(page, /valid citation/);
  assert.match(page, /signal source/);
});

test("discloses why the adaptive agent stopped using tools", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /stop_reason\?: "model_finish" \| "tools_exhausted" \| "step_budget"/);
  assert.match(page, /model stopped after sufficient evidence/);
});

test("scopes persistent knowledge collections to investigations", async () => {
  const [page, collectionsRoute, investigationRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/collections/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/investigate/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /ACTIVE FOR INVESTIGATIONS/);
  assert.match(page, /selectedCollectionIds/);
  assert.match(page, /verifiedCollectionIds/);
  assert.match(page, /Knowledge scope unavailable/);
  assert.match(page, /INDEX INTO COLLECTION/);
  assert.match(collectionsRoute, /\/v1\/knowledge\/collections/);
  assert.match(investigationRoute, /collection_ids/);
});

test("exports portable run and comparison evidence", async () => {
  const [page, exportRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/export/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /Export JSON/);
  assert.match(page, /Export verified evidence/);
  assert.match(exportRoute, /\/v1\/runs\/\$\{encodeURIComponent\(runId\)\}\/export/);
  assert.match(exportRoute, /content-disposition/);
});

test("evaluates saved model runs as a multi-incident suite", async () => {
  const [page, route] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/evaluate/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(page, /SUITE EVALUATION/);
  assert.match(page, /latestModelRuns/);
  assert.match(page, /95% CI/);
  assert.match(page, /Download verified JSON/);
  assert.match(page, /suiteReport\.integrity\.digest/);
  assert.match(route, /\/v1\/evaluation-suites/);
});
