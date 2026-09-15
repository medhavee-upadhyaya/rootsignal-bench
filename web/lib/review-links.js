const RUN_ID = /^[a-f0-9]{32}$/;

export function parseReviewLink(search) {
  const params = new URLSearchParams(search);
  const referenceRunId = params.get("run");
  const candidateRunId = params.get("compare_to");
  if (!referenceRunId || !candidateRunId) return null;
  if (!RUN_ID.test(referenceRunId) || !RUN_ID.test(candidateRunId)) return null;
  if (referenceRunId === candidateRunId) return null;
  return { referenceRunId, candidateRunId };
}

export function buildReviewLink(baseUrl, referenceRunId, candidateRunId) {
  if (!RUN_ID.test(referenceRunId) || !RUN_ID.test(candidateRunId) || referenceRunId === candidateRunId) {
    throw new Error("Two valid, different run IDs are required");
  }
  const url = new URL(baseUrl);
  url.search = "";
  url.hash = "runs";
  url.searchParams.set("run", referenceRunId);
  url.searchParams.set("compare_to", candidateRunId);
  return url.toString();
}
