# Local model runtime

The working development configuration uses Qwen3 1.7B in GGUF format through llama.cpp's OpenAI-compatible server. The compact model fits laptop development constraints; it is not the leaderboard target.

The local runtime and model are intentionally stored under `work/` and excluded from Git because together they exceed 500 MB. The API is configured through `INCIDENTLAB_LLM_URL` and `INCIDENTLAB_MODEL`, so hosted endpoints and vLLM can replace the laptop server without application changes.

For a public benchmark result, record the exact model digest, quantization, context size, hardware, prompt digest, code revision, latency, token counts, and evaluation schema. Do not compare the oracle-backed deterministic plumbing baseline to a model-backed run.

Run a live-model evaluation with:

```bash
python -m evals.live --fixtures fixtures/incidents
```

The small development model is expected to fail some reasoning and citation checks. Those failures are the baseline for fine-tuning and model-selection experiments, not defects to hide.
