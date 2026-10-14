export type PlaygroundEvidence = { id: string; source: string; content: string; score: number };
export const playgroundIncident: { id: string; title: string; summary: string };
export const playgroundDocuments: Array<Omit<PlaygroundEvidence, "score">>;
export function retrievePlaygroundEvidence(query: string, limit?: number): PlaygroundEvidence[];
export function deterministicPlaygroundControl(query: string): { root_cause: string; confidence: number; citations: string[]; remediation: string[]; evidence: PlaygroundEvidence[]; model: string };
export function buildPlaygroundPrompt(query: string, evidence: PlaygroundEvidence[]): string;
export function parsePlaygroundModelResult(content: string, evidence: PlaygroundEvidence[]): { root_cause: string; confidence: number; citations: string[]; invalid_citations: unknown[]; remediation: string[]; evidence: PlaygroundEvidence[] };
