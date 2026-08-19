from __future__ import annotations

from collections.abc import Iterable
import json
import urllib.request

from .models import Incident, ToolCall


class BaselinePolicy:
    """Transparent baseline. It provides a lower bound, not simulated intelligence."""

    def plan(self, incident: Incident) -> Iterable[ToolCall]:
        service = incident.summary.split()[0] if incident.summary else ""
        yield ToolCall("query_metrics", {})
        yield ToolCall("query_logs", {"service": service})
        yield ToolCall("query_deployments", {"service": service})
        yield ToolCall("search_runbooks", {"query": incident.summary})


class OpenAICompatiblePolicy:
    """Policy adapter for vLLM and other OpenAI-compatible chat servers."""

    def __init__(self, base_url: str, model: str, api_key: str = "local", timeout: float = 30.0) -> None:
        self.url = base_url.rstrip("/") + "/v1/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def plan(self, incident: Incident) -> Iterable[ToolCall]:
        from .tools import TOOL_SCHEMAS

        prompt = {
            "incident": {"title": incident.title, "summary": incident.summary},
            "available_tools": TOOL_SCHEMAS,
            "instruction": "Return a JSON array of diagnostic tool calls with name and arguments.",
        }
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "You are a read-only production incident investigator."},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json", "authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.load(response)
        content = json.loads(body["choices"][0]["message"]["content"])
        raw_calls = content.get("calls", content if isinstance(content, list) else [])
        for call in raw_calls:
            yield ToolCall(str(call["name"]), dict(call.get("arguments", {})))
