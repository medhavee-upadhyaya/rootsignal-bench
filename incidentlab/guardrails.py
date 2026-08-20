from __future__ import annotations

import json
import re

from .models import ToolCall

TOOL_ARGUMENTS = {
    "query_logs": {"service"},
    "query_metrics": {"name"},
    "query_deployments": {"service"},
    "search_runbooks": {"query"},
}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_tool_call(call: ToolCall, maximum_length: int = 1000) -> ToolCall | None:
    """Allowlist a read-only tool call and normalize its bounded arguments."""
    allowed_arguments = TOOL_ARGUMENTS.get(call.name)
    if allowed_arguments is None or not isinstance(call.arguments, dict):
        return None
    sanitized: dict[str, str] = {}
    for name, value in call.arguments.items():
        if name not in allowed_arguments:
            continue
        clean = CONTROL_CHARACTERS.sub("", str(value)).strip()[:maximum_length]
        sanitized[name] = clean
    return ToolCall(call.name, sanitized)


def tool_call_key(call: ToolCall) -> str:
    return f"{call.name}:{json.dumps(call.arguments, sort_keys=True, separators=(',', ':'))}"
