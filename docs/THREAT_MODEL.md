# Threat model

## Protected assets

Production telemetry, credentials, tenant boundaries, tool permissions, model endpoints, and the integrity of investigation reports.

## Primary threats

- Prompt injection embedded in logs or runbooks
- Secret or personal-data exfiltration through model context
- Cross-tenant retrieval
- Unbounded tool loops and denial of service
- Fabricated evidence or citations
- Malicious fixture contributions and dataset poisoning
- Supply-chain compromise of models, images, or dependencies

## Controls

Tools are allowlisted and typed, call counts are bounded, evidence preserves provenance, fixture IDs are path-safe, containers run non-root with a read-only filesystem, and benchmark oracles stay outside model context. Production adapters must additionally enforce tenant filters, redact secrets before inference, pin artifacts by digest, sign result manifests, and require authorization at every tool boundary.

Knowledge documents and custom incident fixtures are screened for common private-key, cloud-key, access-token, bearer-token, and credential-assignment patterns before persistence. Detection is intentionally fail-closed for likely matches, but pattern screening is not a substitute for upstream redaction, a platform secret scanner, or tenant-aware authorization.

When `ROOTSIGNAL_API_KEYS` is configured, all state-changing HTTP methods require a bearer key compared in constant time. The web proxy reads its backend key only from the server environment. Authentication is deliberately optional for local development, so an internet-facing deployment without this variable is unsafe and unsupported.

## Explicit non-goals

The reference implementation does not execute shell commands, modify infrastructure, or claim suitability for unsupervised remediation.
