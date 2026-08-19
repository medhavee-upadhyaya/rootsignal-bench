# Architecture decisions

## Replaceable policy boundary

The investigator owns budgets, tool execution, and evidence collection. A policy only proposes typed calls. This allows identical fixtures to compare deterministic, hosted, and local fine-tuned policies.

## Evidence before synthesis

Tools return immutable evidence with provenance. Synthesis consumes this ledger, enabling citation checks and making unsupported claims detectable.

## Dependency-free core

The benchmark, tools, retrieval baseline, CLI, and tests use the Python standard library. API, telemetry exporters, and training stacks are optional groups so contributors can run evaluation without GPU or framework installation.

## OpenAI-compatible inference boundary

Model-serving adapters should target a documented chat/tool-call contract rather than a server-specific SDK. This makes vLLM and hosted endpoints comparable while preserving the benchmark harness.
