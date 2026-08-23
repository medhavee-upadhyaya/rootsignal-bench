# Benchmark design

RootSignal Bench measures investigation behavior rather than stylistic similarity.

The public corpus contains 26 synthetic incidents spanning 26 failure classes:
6 easy, 10 medium, and 10 hard. Each fixture is licensed CC0-1.0 and carries a
separate oracle that is excluded from model context. The machine-readable
[fixture audit](../benchmarks/results/fixture-audit.json) records the integrity
checks and corpus distribution.

## Fixture anatomy

The public observation contains the incident summary, telemetry, runbooks, and distractors. The oracle contains the root cause, required evidence, remediation criteria, and expected tools. Runtime adapters must not place the oracle in the model context. Every fixture also declares its failure class, difficulty, license, and synthetic-data status.

## Metrics

- **Root-cause score:** lexical baseline today; semantic and human grading are planned.
- **Tool selection:** recall over tools required to resolve the incident.
- **Evidence coverage:** required facts present in the evidence ledger.
- **Remediation coverage:** required corrective actions represented in the answer.
- **Overall:** 35% root cause, 20% tools, 25% evidence, and 20% remediation.

These weights are versioned. Scores from different schema or rubric versions must not be compared directly.

## Leakage controls

Fixtures are split by incident template, not only by rendered example. Dataset generation should keep evaluation templates out of training. Public leaderboard submissions must record dataset hashes, model identity, prompt/configuration digest, hardware, and code revision.

`python -m evals.validate_fixtures --fixtures fixtures/incidents` enforces the fixture schema, unique incident IDs, unique public observations, non-empty telemetry/runbooks/oracles, explicit provenance metadata, recognized expected tools, required-evidence grounding, coverage of all difficulty levels, and absence of an exact root-cause string in the public observation. Exact-string detection is a minimum leakage control, not proof against semantic contamination; proposed fixtures still require review.

## Adversarial tool-use contract

`python -m evals.adversarial --minimum 1.0` verifies that the execution layer
blocks unregistered tools, strips unknown arguments, bounds argument length,
deduplicates repeated calls, and enforces the tool budget. Separate hostile
planner tests verify safe fallback behavior, citation-range validation,
confidence clamping, and evidence fallback when a model returns malformed or
unsupported output.

## Adding an incident

An acceptable incident has a single defensible cause, at least one distractor, a timestamped causal sequence, sufficient observable evidence, safe synthetic data, and remediation criteria. A second reviewer should be able to reproduce the oracle without private knowledge.

Evaluation schema v3 reports aggregate uncertainty and scores sliced by declared failure class and difficulty. A slice containing one fixture is descriptive only and must not be interpreted as a stable population estimate.

## End-to-end contract

The CI suite installs the real API dependency group and must not silently skip API coverage. `tests/test_full_stack.py` sends a request through the ASGI application and real OpenAI-compatible client contract using a deterministic in-process provider. The test covers model planning, bounded tool execution, persistent retrieval, evidence citations, token accounting, observability, correlation headers, and structured provider-failure handling. It does not claim model quality; live-model capability remains a separately measured result.

## Baseline disclosure

The deterministic baseline uses the oracle to test plumbing and rubric behavior. Its root-cause score is not an agent capability result. Any published model score must use an adapter that receives only public observations.
