import assert from "node:assert/strict";
import test from "node:test";
import { findControlAgentPair } from "../lib/run-pairing.js";

const run = (run_id, mode, incident_id = "checkout", fixture_sha256 = "fixture-a") => ({
  run_id, mode, incident_id, fixture_sha256,
});

test("selects a control reference and model candidate for the same fixture", () => {
  const pair = findControlAgentPair([
    run("newest-agent", "model"),
    run("irrelevant-control", "baseline", "billing"),
    run("matching-control", "baseline"),
    run("older-agent", "model"),
  ]);
  assert.deepEqual(pair, {
    referenceRunId: "matching-control",
    candidateRunId: "newest-agent",
  });
});

test("never fabricates a pair from same-mode or mismatched-fixture runs", () => {
  assert.equal(findControlAgentPair([run("one", "baseline"), run("two", "baseline")]), null);
  assert.equal(findControlAgentPair([
    run("agent", "model", "checkout", "fixture-new"),
    run("control", "baseline", "checkout", "fixture-old"),
  ]), null);
});
