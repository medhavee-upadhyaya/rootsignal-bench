export const playgroundIncident = {
  id: "checkout-latency-v183",
  title: "Checkout latency after deployment v1.8.3",
  summary: "Checkout p95 latency rose from 420 ms to 2.8 s shortly after deployment v1.8.3.",
};

export const playgroundDocuments = [
  { id: "metric-latency", source: "metrics", content: "checkout.latency_p95_ms rose from 420 to 2800 at 14:07 UTC; request volume remained flat." },
  { id: "metric-pool", source: "metrics", content: "database.pool_wait_ms rose from 18 to 1910 while CPU and memory stayed below 55 percent." },
  { id: "log-timeout", source: "logs", content: "checkout-api emitted acquire connection timeout after 2000ms for 31 percent of requests." },
  { id: "deploy-v183", source: "deployments", content: "checkout-api v1.8.3 deployed at 14:03 UTC and changed DB_POOL_SIZE from 40 to 8." },
  { id: "runbook-pool", source: "runbook", content: "For pool saturation after a configuration release: restore the last known-safe pool size, roll back if recovery is not visible in five minutes, then add a configuration regression test." },
  { id: "log-payment", source: "logs", content: "payment-provider responses remained below 180ms with no increase in provider errors." },
];

const stopWords = new Set(["the", "a", "an", "to", "of", "for", "after", "is", "in", "and", "what"]);

function tokens(value) {
  return new Set(value.toLowerCase().match(/[a-z0-9]+/g)?.filter((token) => !stopWords.has(token)) || []);
}

export function retrievePlaygroundEvidence(query, limit = 5) {
  const queryTokens = tokens(query);
  return playgroundDocuments
    .map((document) => {
      const documentTokens = tokens(`${document.source} ${document.content}`);
      const overlap = [...queryTokens].filter((token) => documentTokens.has(token)).length;
      const incidentBoost = /latency|checkout|deployment|pool|database/.test(document.content.toLowerCase()) ? 0.25 : 0;
      return { ...document, score: overlap + incidentBoost };
    })
    .sort((left, right) => right.score - left.score || left.id.localeCompare(right.id))
    .slice(0, limit);
}

export function deterministicPlaygroundControl(query) {
  const evidence = retrievePlaygroundEvidence(query);
  return {
    root_cause: "Deployment v1.8.3 reduced DB_POOL_SIZE from 40 to 8, saturating the checkout database connection pool.",
    confidence: 0.97,
    citations: ["deploy-v183", "metric-pool", "log-timeout"],
    remediation: ["Restore DB_POOL_SIZE to 40 and roll back v1.8.3 if latency does not recover within five minutes.", "Add a configuration regression test and alert on connection-pool wait time."],
    evidence,
    model: "deterministic-control",
  };
}

export function buildPlaygroundPrompt(query, evidence) {
  const context = evidence.map((item) => `[${item.id}] ${item.source}: ${item.content}`).join("\n");
  return `You are an incident-response investigator. Use only the supplied evidence. Do not invent observations.\n\nIncident: ${playgroundIncident.summary}\nQuestion: ${query}\n\nEvidence:\n${context}\n\nReturn only JSON with this exact shape: {"root_cause":"string","confidence":0.0,"citations":["evidence-id"],"remediation":["string"]}. Cite only IDs shown above. If evidence is insufficient, say so and lower confidence.`;
}

export function parsePlaygroundModelResult(content, evidence) {
  const cleaned = content.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const parsed = JSON.parse(cleaned);
  const validIds = new Set(evidence.map((item) => item.id));
  if (typeof parsed.root_cause !== "string" || !parsed.root_cause.trim()) throw new Error("Model response omitted root_cause");
  if (!Array.isArray(parsed.citations) || !Array.isArray(parsed.remediation)) throw new Error("Model response has an invalid evidence schema");
  const citations = parsed.citations.filter((id) => typeof id === "string" && validIds.has(id));
  return {
    root_cause: parsed.root_cause.trim(),
    confidence: Math.max(0, Math.min(1, Number(parsed.confidence) || 0)),
    citations,
    invalid_citations: parsed.citations.filter((id) => typeof id !== "string" || !validIds.has(id)),
    remediation: parsed.remediation.filter((item) => typeof item === "string" && item.trim()).map((item) => item.trim()),
    evidence,
  };
}
