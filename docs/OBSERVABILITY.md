# Production observability

RootSignal exposes low-cardinality Prometheus metrics at `/metrics`, emits JSON log events carrying the request ID, and creates an OpenTelemetry investigation span when the optional observability dependencies are installed. The Grafana dashboard and Prometheus alerts under `deploy/` are versioned with the application.

## Signals

| Signal | Purpose |
|---|---|
| HTTP requests by route and status class | Traffic and error-rate SLOs |
| Investigation duration histogram | p50/p95 latency and saturation |
| Active investigations | Concurrency and overload diagnosis |
| Prompt and completion tokens | Model usage and capacity |
| Retrieved chunks and agent steps | RAG and agent behavior |
| Invalid citations | Grounding-quality regression |
| Policy fallback steps | Model planner degradation |

Request IDs appear in responses and structured logs, but never in metric labels. Unknown URL paths are collapsed to `other` to prevent unbounded cardinality. Prompts, evidence, credentials, and document contents are not logged.

## High error rate

Check readiness, model-server connectivity, and structured `http_request` events for the affected route. Correlate a failure using `X-Request-ID`. Roll back a recent application or model change if the error began immediately after deployment.

## High latency

Compare active investigations, model token rate, and the inference concurrency benchmark. Determine whether time is spent in model serving, retrieval, or queueing before increasing replicas or model concurrency.

## Citation failures

Inspect retrieval evaluation and recent knowledge-base changes. Do not suppress the alert by accepting unsupported citations. Re-run the fixed evaluation fixtures before deploying a prompt, model, or retrieval change.

## Planner fallbacks

Confirm model-server health and inspect structured investigation summaries. A fallback spike can indicate invalid model JSON, unavailable tool choices, or inference failures. Use the adversarial suite before modifying guardrails.

Readiness returns HTTP 503 when fixtures or the model server are unavailable, allowing Kubernetes to remove the pod from service. Liveness only confirms that the API process is responsive.
