# Architecture decisions

## Product boundary

RootSignal separates public incident observations from private evaluation oracles. Built-in fixtures and validated custom incidents enter the same catalog, investigation, persistence, comparison, and export path. The deterministic control may use the oracle and is labeled accordingly; the independent model agent never receives it.

## Replaceable inference boundary

The model agent owns bounded planning, tool execution, retrieval, and evidence collection while the inference client only produces structured model generations. This allows identical fixtures and scorecards to compare local or hosted OpenAI-compatible model servers.

## Evidence before synthesis

Tools return immutable evidence with provenance. Synthesis consumes this ledger, enabling citation checks and making unsupported claims detectable.

## Dependency-free core

The benchmark, tools, retrieval baseline, CLI, and tests use the Python standard library. API, telemetry exporters, and training stacks are optional groups so contributors can run evaluation without GPU or framework installation.

## OpenAI-compatible inference boundary

Model-serving adapters should target a documented chat/tool-call contract rather than a server-specific SDK. This makes vLLM and hosted endpoints comparable while preserving the benchmark harness.

## Scoped retrieval

Documents are content-addressed once and attached to one or more durable knowledge collections. Every model investigation declares its active collections, preventing unrelated runbooks from silently entering retrieval. Legacy global-index documents are quarantined during migration.

## Immutable experiments and evidence

Successful runs are stored as immutable snapshots with the incident hash, model, mode, request ID, retrieval configuration, timing, tools, citations, and result. Comparisons reject different incidents or fixture revisions. Portable JSON exports include their scorecard and an offline-verifiable SHA-256 digest; this detects tampering but is not an identity signature.
