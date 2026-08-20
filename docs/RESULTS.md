# Measured Results

RootSignal separates deterministic infrastructure checks from model quality. A
result is publishable only when its command, fixture count, model identity,
hardware context, and machine-readable output are available.

Evaluation schema v3 reports deterministic nonparametric bootstrap confidence intervals for every aggregate metric. Candidate changes are compared to a baseline by incident ID using paired deltas, which controls for fixture difficulty and refuses mismatched fixture sets.

```bash
python -m evals.run --fixtures fixtures/incidents --output work/baseline.json
python -m evals.run --fixtures fixtures/incidents --output work/candidate.json
python -m evals.compare work/baseline.json work/candidate.json \
  --metric overall --max-regression 0.01 \
  --minimum-lower-bound -0.02 --minimum-probability 0.80
```

The comparison reports per-incident deltas, wins/ties/losses, mean and median delta, a bootstrap confidence interval, and bootstrap probability of improvement. The CI is uncertainty over this fixture sample, not evidence that five synthetic incidents represent all production failures. Promotion can independently gate mean regression tolerance, the confidence-interval lower bound, and probability of improvement.

## Retrieval

Command:

```bash
python -m evals.retrieval --fixtures fixtures/incidents --k 2 --ablation
```

| Corpus | Queries | Recall@2 | MRR |
|---|---:|---:|---:|
| Public incident runbooks | 5 | 1.000 | 0.900 |

### Strategy ablation

| Strategy | Recall@2 | MRR |
|---|---:|---:|
| FTS5 lexical | 1.000 | 0.900 |
| Hashed semantic | 0.400 | 0.300 |
| Weighted RRF hybrid | 1.000 | 0.900 |
| Hybrid + relevance reranker | 1.000 | 0.900 |

The retriever exposes lexical, semantic, hybrid, and reranked strategies. The
default combines SQLite FTS5 with deterministic hashed semantic features using
weighted reciprocal-rank fusion, then applies an auditable term-and-bigram
relevance reranker. The ablation command reports every strategy side by side
and fails CI if default Recall@2 falls below `1.00`. This compact implementation is intended
for reproducible evaluation; production deployments can replace the semantic
encoder without changing provenance or scorecard contracts.

The small public corpus does not show a gain from reranking, and the compact
semantic baseline underperforms lexical retrieval. Both results are retained to
prevent a more complex pipeline from being presented as an automatic quality
improvement.

## Live local model

| Model | Incidents | Overall | Tool selection | Evidence coverage | Citation validity | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-1.7B GGUF, llama.cpp CPU | 5 | 0.662 | 0.950 | 0.650 | 1.000 | 8.8 s |

Hardware: Apple M4, 16 GB unified memory. These measurements are development
evidence, not universal performance claims. The complete result is stored in
`benchmarks/results/qwen3-1.7b-local.json`.

## Deterministic plumbing baseline

The deterministic baseline currently scores `0.940` across five fixtures under
scorecard schema v3. It uses each fixture oracle for synthesis and therefore
must never be compared with a model-quality score. Its purpose is regression
testing for tools, evidence transport, evaluation, and API behavior.

## Fine-tuning and GPU inference

A LoRA tool-selector training run was measured on a Google Colab Tesla T4
(15,360 MiB) against source commit `c60917c2b89d44c814eff35cc230567b60dbaa89`.
Qwen2.5-0.5B-Instruct revision `7ae557604adf67be50417f59c2c2f167def9a775`
trained for three epochs on 16 examples and evaluated on four incident-template-
isolated examples. Training loss was `2.6024`, held-out loss was `1.9810`, and
the measured training runtime was `10.0844s` (`32.448s` end-to-end wall time).
The validated [evidence](../results/gpu/training-evidence.json),
[training manifest](../results/gpu/training-manifest.json), and
[dataset manifest](../results/gpu/dataset-manifest.json) disclose hashes,
hardware, seed, split, configuration, and runtime metadata. The clean
[Colab notebook](../notebooks/rootsignal_gpu_training.ipynb) reproduces the run.
Training loss alone is not claimed as proof of downstream improvement.

A streaming vLLM 0.27.1 inference sweep was also measured on a Tesla T4 using
the same pinned Qwen model revision in float16. Across 80 requests, all requests
succeeded. At concurrency 8, output throughput reached `1,019.214 tokens/s`,
p95 TTFT was `53.682ms`, and p95 end-to-end latency was `434.991ms`. The full
[machine-readable sweep](../benchmarks/results/vllm-t4-qwen2.5-0.5b.json),
[hardware/software evidence](../results/gpu/inference-evidence.json), and clean
[Colab notebook](../notebooks/rootsignal_vllm_benchmark.ipynb) disclose the
protocol and environment. These are specific T4 measurements, not universal
performance claims.
