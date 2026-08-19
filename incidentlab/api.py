from __future__ import annotations

import os
import json
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Response
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install RootSignal with the 'api' dependency group") from exc

from .agent import Investigator
from .fixtures import load_incident
from .knowledge import KnowledgeBase
from .llm import OllamaClient
from .observability import METRICS
from .rag_agent import GroundedAgent

FIXTURE_ROOT = Path(os.getenv("INCIDENTLAB_FIXTURES", "fixtures/incidents")).resolve()
KNOWLEDGE = KnowledgeBase(os.getenv("INCIDENTLAB_DB", "work/incidentlab.db"))
BENCHMARK_PATH = Path(os.getenv("INCIDENTLAB_BENCHMARK", "benchmarks/results/qwen3-1.7b-local.json"))
LLM = OllamaClient(
    os.getenv("INCIDENTLAB_LLM_URL", "http://127.0.0.1:11434"),
    os.getenv("INCIDENTLAB_MODEL", "qwen3:1.7b"),
)
app = FastAPI(title="RootSignal API", version="0.2.0")


class InvestigationRequest(BaseModel):
    incident_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    query: str | None = Field(default=None, min_length=3, max_length=2000)


class KnowledgeRequest(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20, max_length=1_000_000)


def _incident(incident_id: str):
    paths = list(FIXTURE_ROOT.glob("*.yaml")) + list(FIXTURE_ROOT.glob("*.json"))
    return next(
        (candidate for path in paths if (candidate := load_incident(path)).incident_id == incident_id), None
    )


def _seed_knowledge() -> None:
    for path in [*FIXTURE_ROOT.glob("*.yaml"), *FIXTURE_ROOT.glob("*.json")]:
        incident = load_incident(path)
        for runbook in incident.runbooks:
            KNOWLEDGE.ingest(f"runbook/{runbook.get('id', 'unknown')}", runbook.get("content", ""))


_seed_knowledge()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness() -> dict[str, object]:
    return {
        "status": "ready" if FIXTURE_ROOT.exists() and LLM.healthy() else "not_ready",
        "model": LLM.model,
        "model_server": LLM.healthy(),
        "knowledge": KNOWLEDGE.stats(),
    }


@app.get("/v1/system")
def system() -> dict[str, object]:
    return {
        "llm": {"provider": "openai-compatible", "model": LLM.model, "healthy": LLM.healthy()},
        "retrieval": {"engine": "sqlite-fts5", **KNOWLEDGE.stats()},
        "tools": ["query_metrics", "query_logs", "query_deployments", "retrieve_knowledge"],
        "inference": {"development": "llama.cpp", "production": "openai-compatible/vllm"},
    }


@app.get("/v1/benchmarks/latest")
def latest_benchmark() -> dict[str, object]:
    if not BENCHMARK_PATH.exists():
        raise HTTPException(status_code=404, detail="No benchmark result published")
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


@app.post("/v1/knowledge")
def ingest_knowledge(request: KnowledgeRequest) -> dict[str, object]:
    return KNOWLEDGE.ingest(request.source, request.text)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(METRICS.prometheus(), media_type="text/plain; version=0.0.4")


@app.post("/v1/investigations")
def investigate(request: InvestigationRequest) -> dict[str, object]:
    incident = _incident(request.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    query = request.query or incident.summary
    with METRICS.investigation():
        try:
            return GroundedAgent(KNOWLEDGE, LLM).investigate(query, incident)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Local model unavailable: {exc}") from exc


@app.post("/v1/baselines/deterministic")
def deterministic_baseline(request: InvestigationRequest) -> dict[str, object]:
    incident = _incident(request.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    return Investigator().investigate(incident).as_dict()
