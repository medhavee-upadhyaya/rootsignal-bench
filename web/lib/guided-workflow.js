export const GUIDED_STEP_IDS = ["incident", "knowledge", "control", "agent", "compare", "export"];

/**
 * Derive the guided workflow from verified product state. A step only completes
 * when its underlying artifact exists; navigation alone never advances it.
 */
export function getGuidedWorkflow(state) {
  const completed = {
    incident: Boolean(state.incidentId),
    knowledge: state.collectionCount > 0,
    control: Boolean(state.controlRunId),
    agent: Boolean(state.agentRunId),
    compare: Boolean(state.comparisonComplete),
    export: Boolean(state.exported),
  };
  const current = GUIDED_STEP_IDS.find((id) => !completed[id]) ?? null;
  const steps = GUIDED_STEP_IDS.map((id) => ({
    id,
    status: completed[id]
      ? "complete"
      : id === current && id === "agent" && !state.modelAvailable
        ? "blocked"
        : id === current
          ? "current"
          : "pending",
  }));
  return {
    complete: current === null,
    current,
    completedCount: GUIDED_STEP_IDS.filter((id) => completed[id]).length,
    steps,
  };
}
