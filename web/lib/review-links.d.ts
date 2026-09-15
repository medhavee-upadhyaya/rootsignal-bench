export type ReviewPair = { referenceRunId: string; candidateRunId: string };
export function parseReviewLink(search: string): ReviewPair | null;
export function buildReviewLink(baseUrl: string, referenceRunId: string, candidateRunId: string): string;
