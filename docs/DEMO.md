# End-to-end demo

This walkthrough demonstrates the complete RootSignal lifecycle without presenting deterministic plumbing as model capability.

## 1. Start the product

Run an OpenAI-compatible local model server if you want independent model runs, then start the stack:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The deterministic control works without a model; the workspace reports model availability separately.

## 2. Bring an incident

Choose one of the 26 built-in incidents or open **Create**, use the guided builder, and provide public observations plus a private expected root cause, evidence, and remediation. RootSignal validates and persists the scenario while keeping its oracle out of catalog responses.

## 3. Add operational context

Under **Knowledge**, create a collection, index a runbook or postmortem, and select which collections are active for investigations. Collection scoping prevents unrelated documents from contaminating retrieval.

## 4. Run and audit

Run the **Oracle-backed reference** to verify the pipeline, then run **Independent model** to assess actual model behavior. Inspect every tool call, evidence item, citation, remediation, latency, token count, retrieval count, and reproducibility identifier.

## 5. Compare and export

Open two matching saved runs, compare them, and export the evidence bundle. Verify the downloaded file offline:

```bash
python -m incidentlab.evidence_bundle rootsignal-RUN_ID.json
```

Changing any value in the JSON causes integrity verification to fail.

## 6. Replay the offline CLI baseline

```bash
python -m incidentlab.cli investigate fixtures/incidents/checkout_latency.yaml
```

Inspect the tool calls, evidence ledger, cited cause, remediation, and explicit baseline limitation in the output.

## 7. Measure behavior

```bash
python -m evals.run --fixtures fixtures/incidents --minimum 0.80
python -m evals.retrieval --fixtures fixtures/incidents --k 2 --ablation
python -m evals.adversarial --minimum 1.0
```

These commands separately expose diagnosis quality, retrieval behavior, and tool-use guardrails. Machine-readable results make regressions reviewable in a pull request.

## 8. Build training evidence

```bash
python -m training.build_dataset --fixtures fixtures/incidents --output-dir work/dataset
python -m training.validate_artifacts --dataset-manifest work/dataset/dataset_manifest.json
```

The manifest proves which source revision, split unit, seed, examples, and hashes produced the dataset. Actual LoRA training is optional and requires the `train` dependency group plus suitable hardware.

## 9. Inspect production signals

Open `http://localhost:8000/metrics` after an investigation. The exported signals include request/error counts, latency, tokens, retrieval chunks, agent steps, invalid citations, and planner fallbacks. Import the versioned Grafana dashboard and Prometheus alerts from `deploy/` for an operational view.

## 10. Benchmark inference

Follow [INFERENCE_BENCHMARK.md](INFERENCE_BENCHMARK.md) against a real vLLM deployment. Publish the complete concurrency sweep and disclosed hardware metadata; never substitute or invent GPU measurements.

## What this proves

The demo provides inspectable evidence for an LLM application, bounded agent tool use, backend engineering, RAG, evaluation, a reproducible training path, inference performance work, observability, and deployment. Public adoption and third-party model results remain community outcomes rather than implementation claims.
