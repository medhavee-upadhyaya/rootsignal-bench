import assert from "node:assert/strict";
import test from "node:test";

import { parseTelemetryBundle } from "../lib/telemetry-import.js";

test("normalizes a telemetry envelope into incident form fields", () => {
  const imported = parseTelemetryBundle(JSON.stringify({
    id: "checkout-live",
    title: "Checkout latency",
    summary: "Checkout p95 increased after deployment",
    telemetry: {
      metrics: { "checkout.p95_ms": 1800, "checkout.error_rate": "12%" },
      logs: ["checkout ERROR timeout", { level: "WARN", message: "pool wait" }],
      deployments: [{ service: "checkout", version: "v2" }],
    },
    runbooks: [{ content: "Compare pool capacity with the previous release." }],
  }));
  assert.equal(imported.id, "checkout-live");
  assert.equal(imported.metrics, "checkout.p95_ms=1800\ncheckout.error_rate=12%");
  assert.match(imported.logs, /\{"level":"WARN","message":"pool wait"\}/);
  assert.equal(imported.counts.metrics, 2);
  assert.equal(imported.counts.logs, 2);
  assert.equal(imported.counts.deployments, 1);
  assert.match(imported.runbook, /pool capacity/);
});

test("accepts a flat telemetry object", () => {
  const imported = parseTelemetryBundle(JSON.stringify({
    metrics: { cpu: 91 },
    logs: ["worker WARN saturated", "worker ERROR timeout"],
    deployments: ["worker v3 deployed"],
  }));
  assert.equal(imported.metrics, "cpu=91");
  assert.equal(imported.title, "");
});

test("rejects malformed and incomplete bundles", () => {
  assert.throws(() => parseTelemetryBundle("not-json"), /valid JSON/);
  assert.throws(() => parseTelemetryBundle(JSON.stringify({ metrics: {}, logs: [], deployments: [] })), /Metrics/);
  assert.throws(() => parseTelemetryBundle("x".repeat(1_000_001)), /1 MB/);
});
