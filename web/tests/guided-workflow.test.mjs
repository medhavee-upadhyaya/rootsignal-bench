import assert from "node:assert/strict";
import test from "node:test";
import { getGuidedWorkflow } from "../lib/guided-workflow.js";

const initial = {
  incidentId: "",
  collectionCount: 0,
  controlRunId: null,
  agentRunId: null,
  modelAvailable: true,
  comparisonComplete: false,
  exported: false,
};

test("advances only when real workflow artifacts exist", () => {
  assert.equal(getGuidedWorkflow(initial).current, "incident");
  assert.equal(getGuidedWorkflow({ ...initial, incidentId: "checkout", collectionCount: 1 }).current, "control");
  assert.equal(getGuidedWorkflow({ ...initial, incidentId: "checkout", collectionCount: 1, controlRunId: "run-control" }).current, "agent");
  assert.equal(getGuidedWorkflow({ ...initial, incidentId: "checkout", collectionCount: 1, controlRunId: "run-control", agentRunId: "run-agent" }).current, "compare");
  assert.equal(getGuidedWorkflow({ ...initial, incidentId: "checkout", collectionCount: 1, controlRunId: "run-control", agentRunId: "run-agent", comparisonComplete: true }).current, "export");
  assert.equal(getGuidedWorkflow({ ...initial, incidentId: "checkout", collectionCount: 1, controlRunId: "run-control", agentRunId: "run-agent", comparisonComplete: true, exported: true }).complete, true);
});

test("marks the agent step blocked when no model endpoint is healthy", () => {
  const workflow = getGuidedWorkflow({ ...initial, incidentId: "checkout", collectionCount: 1, controlRunId: "run-control", modelAvailable: false });
  assert.equal(workflow.current, "agent");
  assert.equal(workflow.steps.find((step) => step.id === "agent")?.status, "blocked");
});
