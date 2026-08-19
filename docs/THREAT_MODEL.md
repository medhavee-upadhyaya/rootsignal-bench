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

## Explicit non-goals

The reference implementation does not execute shell commands, modify infrastructure, or claim suitability for unsupervised remediation.
