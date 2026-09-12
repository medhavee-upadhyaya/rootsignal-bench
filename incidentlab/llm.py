from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Generation:
    content: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class ModelReadiness:
    healthy: bool
    status: str
    message: str


class OpenAICompatibleClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen3:0.6b") -> None:
        self.base_url = base_url.rstrip("/")
        self.url = self.base_url + "/v1/chat/completions"
        self.model = model

    def generate_json(self, system: str, user: str, max_tokens: int = 500) -> Generation:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": "/no_think " + system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        started = time.perf_counter()
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers={"content-type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.load(response)
        return Generation(
            content=body["choices"][0]["message"]["content"],
            model=body.get("model", self.model),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            prompt_tokens=int(body.get("usage", {}).get("prompt_tokens", 0)),
            completion_tokens=int(body.get("usage", {}).get("completion_tokens", 0)),
        )

    def probe(self) -> ModelReadiness:
        try:
            response = urllib.request.urlopen(self.base_url + "/v1/models", timeout=2)
        except Exception:
            return ModelReadiness(False, "server_unreachable", "Start the model server and verify its port.")
        try:
            with response:
                if response.status != 200:
                    return ModelReadiness(False, "server_error", "Model server returned an unhealthy status.")
                payload = json.load(response)
            models = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(models, list):
                return ModelReadiness(False, "incompatible_server", "Model server returned an invalid model catalog.")
            available = {
                str(item["id"])
                for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            if self.model not in available:
                return ModelReadiness(False, "model_not_loaded", f"Load the configured model: {self.model}.")
            return ModelReadiness(True, "ready", f"{self.model} is loaded and ready.")
        except Exception:
            return ModelReadiness(False, "incompatible_server", "Model server returned an invalid model catalog.")

    def healthy(self) -> bool:
        return self.probe().healthy


# Backwards-compatible name retained for integrations created against v0.1.
OllamaClient = OpenAICompatibleClient
