#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
runtime="$root/work/runtime/Ollama.app/Contents/Resources"
model="$root/work/ollama-models/blobs/sha256-3d0b790534fe4b79525fc3692950408dca41171676ed7e21db57af5c65ef6ab6"

if [[ ! -x "$runtime/llama-server" || ! -f "$model" ]]; then
  echo "Local model runtime is missing. Follow docs/LOCAL_MODEL.md first." >&2
  exit 1
fi

cleanup() {
  kill "${model_pid:-}" "${api_pid:-}" "${web_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$root"
"$runtime/llama-server" --model "$model" --host 127.0.0.1 --port 11434 \
  --device none --no-op-offload --gpu-layers 0 --ctx-size 1024 --no-webui &
model_pid=$!

INCIDENTLAB_MODEL=qwen3:1.7b .venv/bin/uvicorn incidentlab.api:app --host 127.0.0.1 --port 8000 &
api_pid=$!

cd "$root/web"
npm run dev &
web_pid=$!

wait "$model_pid" "$api_pid" "$web_pid"
