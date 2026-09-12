/** Select the newest valid control-to-agent pair from a run history. */
export function findControlAgentPair(runs) {
  for (const candidate of runs) {
    if (candidate.mode !== "model") continue;
    const reference = runs.find((run) => (
      run.mode === "baseline"
      && run.incident_id === candidate.incident_id
      && run.fixture_sha256 === candidate.fixture_sha256
    ));
    if (reference) {
      return { referenceRunId: reference.run_id, candidateRunId: candidate.run_id };
    }
  }
  return null;
}
