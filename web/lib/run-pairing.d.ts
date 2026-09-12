export type PairableRun = {
  run_id: string;
  incident_id: string;
  fixture_sha256: string;
  mode: "baseline" | "model";
};
export function findControlAgentPair(runs: PairableRun[]): {
  referenceRunId: string;
  candidateRunId: string;
} | null;
