# Measured Results

RootSignal separates deterministic infrastructure checks from model quality. A
result is publishable only when its command, fixture count, model identity,
hardware context, and machine-readable output are available.

## Retrieval

Command:

```bash
python -m evals.retrieval --fixtures fixtures/incidents --k 2
```

| Corpus | Queries | Recall@2 | MRR |
|---|---:|---:|---:|
| Public incident runbooks | 5 | 1.000 | 0.900 |

The retriever combines SQLite FTS5 with deterministic hashed semantic features
using weighted reciprocal-rank fusion. This compact implementation is intended
for reproducible evaluation; production deployments can replace the semantic
encoder without changing provenance or scorecard contracts.

## Live local model

| Model | Incidents | Overall | Tool selection | Evidence coverage | Citation validity | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-1.7B GGUF, llama.cpp CPU | 5 | 0.662 | 0.950 | 0.650 | 1.000 | 8.8 s |

Hardware: Apple M4, 16 GB unified memory. These measurements are development
evidence, not universal performance claims. The complete result is stored in
`benchmarks/results/qwen3-1.7b-local.json`.

## Deterministic plumbing baseline

The deterministic baseline currently scores `0.940` across five fixtures under
scorecard schema v2. It uses each fixture oracle for synthesis and therefore
must never be compared with a model-quality score. Its purpose is regression
testing for tools, evidence transport, evaluation, and API behavior.

## Fine-tuning and GPU inference

The repository contains executable LoRA and concurrency benchmark pipelines,
but no adapter or GPU result is claimed yet. Publishing one requires a dataset
digest, split, seed, base-model revision, training metrics, hardware manifest,
and before/after held-out evaluation.
