# End-to-end demo

This walkthrough demonstrates the complete RootSignal lifecycle without presenting deterministic plumbing as model capability.

## 1. Replay the offline baseline

```bash
python -m incidentlab.cli investigate fixtures/incidents/checkout_latency.yaml
```

Inspect the tool calls, evidence ledger, cited cause, remediation, and explicit baseline limitation in the output.

## 2. Measure behavior

```bash
python -m evals.run --fixtures fixtures/incidents --minimum 0.80
python -m evals.retrieval --fixtures fixtures/incidents --k 2 --ablation
python -m evals.adversarial --minimum 1.0
```

These commands separately expose diagnosis quality, retrieval behavior, and tool-use guardrails. Machine-readable results make regressions reviewable in a pull request.

## 3. Build training evidence

```bash
python -m training.build_dataset --fixtures fixtures/incidents --output-dir work/dataset
python -m training.validate_artifacts --dataset-manifest work/dataset/dataset_manifest.json
```

The manifest proves which source revision, split unit, seed, examples, and hashes produced the dataset. Actual LoRA training is optional and requires the `train` dependency group plus suitable hardware.

## 4. Run the product

Start an OpenAI-compatible local model server, then run:

```bash
docker compose up --build
```

Open `http://localhost:3000`, select an incident, run the investigation, inspect citations and tool decisions, and ingest a new operational document to exercise the persistent RAG path.

## 5. Inspect production signals

Open `http://localhost:8000/metrics` after an investigation. The exported signals include request/error counts, latency, tokens, retrieval chunks, agent steps, invalid citations, and planner fallbacks. Import the versioned Grafana dashboard and Prometheus alerts from `deploy/` for an operational view.

## 6. Benchmark inference

Follow [INFERENCE_BENCHMARK.md](INFERENCE_BENCHMARK.md) against a real vLLM deployment. Publish the complete concurrency sweep and disclosed hardware metadata; never substitute or invent GPU measurements.

## What this proves

The demo provides inspectable evidence for an LLM application, bounded agent tool use, backend engineering, RAG, evaluation, a reproducible training path, inference performance work, observability, and deployment. Public adoption and third-party model results remain community outcomes rather than implementation claims.
