export type GuidedStepId = "incident" | "knowledge" | "control" | "agent" | "compare" | "export";
export type GuidedStepStatus = "complete" | "current" | "blocked" | "pending";
export type GuidedWorkflowInput = {
  incidentId: string;
  collectionCount: number;
  controlRunId: string | null;
  agentRunId: string | null;
  modelAvailable: boolean;
  comparisonComplete: boolean;
  exported: boolean;
};
export function getGuidedWorkflow(state: GuidedWorkflowInput): {
  complete: boolean;
  current: GuidedStepId | null;
  completedCount: number;
  steps: Array<{ id: GuidedStepId; status: GuidedStepStatus }>;
};
