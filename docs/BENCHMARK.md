# Benchmark design

RootSignal Bench measures investigation behavior rather than stylistic similarity.

## Fixture anatomy

The public observation contains the incident summary, telemetry, runbooks, and distractors. The oracle contains the root cause, required evidence, remediation criteria, and expected tools. Runtime adapters must not place the oracle in the model context.

## Metrics

- **Root-cause score:** lexical baseline today; semantic and human grading are planned.
- **Tool selection:** recall over tools required to resolve the incident.
- **Evidence coverage:** required facts present in the evidence ledger.
- **Remediation coverage:** required corrective actions represented in the answer.
- **Overall:** 35% root cause, 20% tools, 25% evidence, and 20% remediation.

These weights are versioned. Scores from different schema or rubric versions must not be compared directly.

## Leakage controls

Fixtures are split by incident template, not only by rendered example. Dataset generation should keep evaluation templates out of training. Public leaderboard submissions must record dataset hashes, model identity, prompt/configuration digest, hardware, and code revision.

## Adversarial tool-use contract

`python -m evals.adversarial --minimum 1.0` verifies that the execution layer
blocks unregistered tools, strips unknown arguments, bounds argument length,
deduplicates repeated calls, and enforces the tool budget. Separate hostile
planner tests verify safe fallback behavior, citation-range validation,
confidence clamping, and evidence fallback when a model returns malformed or
unsupported output.

## Adding an incident

An acceptable incident has a single defensible cause, at least one distractor, a timestamped causal sequence, sufficient observable evidence, safe synthetic data, and remediation criteria. A second reviewer should be able to reproduce the oracle without private knowledge.

## Baseline disclosure

The deterministic baseline uses the oracle to test plumbing and rubric behavior. Its root-cause score is not an agent capability result. Any published model score must use an adapter that receives only public observations.
