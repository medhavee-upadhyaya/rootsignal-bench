# Inference benchmark

RootSignal includes a streaming benchmark for vLLM and other OpenAI-compatible model servers. It measures time to first token (TTFT), end-to-end latency, request throughput, output-token throughput, failures, and saturation across a concurrency sweep.

## Run vLLM

Start a server with a pinned model revision:

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --revision <commit> --dtype bfloat16
```

Run the benchmark and identify the actual machine used:

```bash
python -m benchmarks.inference \
  --model Qwen/Qwen2.5-7B-Instruct \
  --model-revision <commit> \
  --hardware "1x NVIDIA L4 24GB" \
  --dtype bfloat16 \
  --requests 50 \
  --concurrency-sweep 1,2,4,8,16 \
  --output work/vllm-result.json
```

Warm-up requests are excluded. Each measured request streams tokens and requests server-side token usage. The command exits nonzero if any concurrency point violates its latency, TTFT, or success-rate SLO.

Compare two runs at matching concurrency points:

```bash
python -m benchmarks.compare work/baseline.json work/candidate.json
```

## Reporting rules

- Pin and report the model revision, server, dtype, quantization, tensor parallelism, and hardware.
- Keep prompt and maximum output length identical between compared runs.
- Publish failures and the full concurrency sweep, not only the fastest point.
- Do not treat laptop llama.cpp measurements as vLLM/GPU results.
- Do not commit model weights, credentials, or machine-specific endpoints.

No GPU result is checked into this repository until it has been measured on the disclosed hardware. The existing Qwen3 laptop scorecard is a model-quality baseline, not a vLLM performance claim.
