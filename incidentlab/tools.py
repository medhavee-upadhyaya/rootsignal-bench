from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import Evidence, Incident
from .retrieval import bm25_search

Tool = Callable[[Incident, dict[str, Any]], list[Evidence]]


def query_logs(incident: Incident, arguments: dict[str, Any]) -> list[Evidence]:
    service = str(arguments.get("service", ""))
    rows = incident.telemetry.get("logs", [])
    return [Evidence("logs", row) for row in rows if not service or service in row]


def query_metrics(incident: Incident, arguments: dict[str, Any]) -> list[Evidence]:
    name = str(arguments.get("name", ""))
    metrics = incident.telemetry.get("metrics", {})
    return [
        Evidence("metrics", f"{key}: {value}")
        for key, value in metrics.items()
        if not name or name.lower() in key.lower()
    ]


def query_deployments(incident: Incident, arguments: dict[str, Any]) -> list[Evidence]:
    service = str(arguments.get("service", ""))
    deployments = incident.telemetry.get("deployments", [])
    return [
        Evidence("deployments", row)
        for row in deployments
        if not service or service.lower() in row.lower()
    ]


def search_runbooks(incident: Incident, arguments: dict[str, Any]) -> list[Evidence]:
    query = str(arguments.get("query", incident.summary))
    return [
        Evidence(f"runbook:{item.get('id', 'unknown')}", str(item.get("content", "")), float(item["score"]))
        for item in bm25_search(query, incident.runbooks)
        if float(item["score"]) > 0
    ]


TOOL_REGISTRY: dict[str, Tool] = {
    "query_logs": query_logs,
    "query_metrics": query_metrics,
    "query_deployments": query_deployments,
    "search_runbooks": search_runbooks,
}


TOOL_SCHEMAS = [
    {"name": "query_logs", "description": "Search incident logs", "arguments": {"service": "string"}},
    {"name": "query_metrics", "description": "Read incident metrics", "arguments": {"name": "string"}},
    {"name": "query_deployments", "description": "Inspect recent deployments", "arguments": {"service": "string"}},
    {"name": "search_runbooks", "description": "Retrieve operational guidance", "arguments": {"query": "string"}},
]
