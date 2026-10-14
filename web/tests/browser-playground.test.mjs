import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { buildPlaygroundPrompt, deterministicPlaygroundControl, parsePlaygroundModelResult, retrievePlaygroundEvidence } from "../lib/browser-playground.js";

test("retrieves bounded incident evidence locally", () => {
  const evidence = retrievePlaygroundEvidence("checkout latency after deployment database pool", 4);
  assert.equal(evidence.length, 4);
  assert.ok(evidence.some((item) => item.id === "deploy-v183"));
  assert.ok(evidence.some((item) => item.id === "metric-pool"));
});

test("builds a grounded prompt with auditable evidence ids", () => {
  const evidence = retrievePlaygroundEvidence("checkout latency", 3);
  const prompt = buildPlaygroundPrompt("What changed?", evidence);
  assert.match(prompt, /Use only the supplied evidence/);
  for (const item of evidence) assert.match(prompt, new RegExp(`\\[${item.id}\\]`));
});

test("rejects hallucinated citations from provider output", () => {
  const evidence = retrievePlaygroundEvidence("database pool", 4);
  const result = parsePlaygroundModelResult(JSON.stringify({ root_cause: "Pool regression", confidence: 2, citations: [evidence[0].id, "invented-id"], remediation: ["Restore the pool"] }), evidence);
  assert.deepEqual(result.citations, [evidence[0].id]);
  assert.deepEqual(result.invalid_citations, ["invented-id"]);
  assert.equal(result.confidence, 1);
});

test("offers a useful deterministic control without an API key", () => {
  const result = deterministicPlaygroundControl("checkout latency after deployment");
  assert.equal(result.model, "deterministic-control");
  assert.ok(result.citations.every((id) => result.evidence.some((item) => item.id === id)));
});

test("keeps visitor credentials in memory and calls the provider directly", async () => {
  const page = await readFile(new URL("../app/playground/page.tsx", import.meta.url), "utf8");
  assert.match(page, /const apiKey = useRef\(""\)/);
  assert.match(page, /https:\/\/openrouter\.ai\/api\/v1\/chat\/completions/);
  assert.match(page, /apiKey\.current = ""/);
  assert.doesNotMatch(page, /localStorage|sessionStorage|document\.cookie/);
  assert.doesNotMatch(page, /appPath\("\/api\//);
});
