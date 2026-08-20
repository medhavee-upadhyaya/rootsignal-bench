# Changelog

All notable changes are documented here. RootSignal follows semantic versioning.

## 0.2.0 — Unreleased

### Application and agents

- Added a complete investigation workspace with knowledge ingestion and benchmark views.
- Replaced the scripted path with a bounded model-driven observe-act loop.
- Added typed tool validation, duplicate suppression, budgets, citation checks, and adversarial tests.

### Retrieval, evaluation, and training

- Added persistent SQLite FTS5 ingestion with provenance, hybrid retrieval, reranking, and ablations.
- Expanded the benchmark to five incident classes with distractors and grading oracles.
- Added live-model, retrieval, citation, and agent-planning evaluations.
- Added template-isolated training splits, dataset hashes, LoRA configuration, artifact manifests, validation, and base-versus-adapter comparison.

### Inference and operations

- Added streaming TTFT, latency, token-throughput, concurrency, comparison, and SLO benchmarks for OpenAI-compatible servers.
- Added structured telemetry, bounded Prometheus metrics, OpenTelemetry spans, alerts, dashboards, and operational runbooks.
- Added hardened API and web containers, Compose, Kubernetes rollout controls, and multi-architecture release images with SBOM and provenance attestations.
- Added CI, dependency and secret scanning, release checks, contributor templates, and reproducibility documentation.

### Measured evidence

- Published a disclosed Qwen3-1.7B llama.cpp laptop baseline, including failures.
- Measured retrieval Recall@2 of 1.000 and MRR of 0.900 on the five public scenarios.
- Kept deterministic plumbing results explicitly separate from model-backed capability claims.

## 0.1.0 — 2026-08-14

- Added the first replayable incident and deterministic plumbing baseline.
- Added typed tools, lexical retrieval, evidence ledger, API, CLI, and metrics.
- Added initial evaluation, dataset generation, training, load-test, container, and CI entry points.
