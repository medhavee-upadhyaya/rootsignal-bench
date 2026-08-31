from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install RootSignal with the 'api' dependency group") from exc

from .agent import Investigator
from .comparison import compare_runs
from .custom_incidents import CustomIncidentStore
from .evidence_bundle import build_evidence_bundle
from .fixtures import load_incident
from .http import RateLimiter, request_id
from .knowledge import KnowledgeBase
from .llm import OllamaClient
from .models import Incident
from .observability import METRICS, log_event, trace_span
from .rag_agent import GroundedAgent
from .runs import ExecutionMode, RunStore

FIXTURE_ROOT = Path(os.getenv("INCIDENTLAB_FIXTURES", "fixtures/incidents")).resolve()
DB_PATH = os.getenv("INCIDENTLAB_DB", "work/incidentlab.db")
KNOWLEDGE = KnowledgeBase(DB_PATH)
RUNS = RunStore(DB_PATH)
CUSTOM_INCIDENTS = CustomIncidentStore(DB_PATH)
BENCHMARK_PATH = Path(os.getenv("INCIDENTLAB_BENCHMARK", "benchmarks/results/qwen3-1.7b-local.json"))
LLM = OllamaClient(
    os.getenv("INCIDENTLAB_LLM_URL", "http://127.0.0.1:11434"),
    os.getenv("INCIDENTLAB_MODEL", "qwen3:1.7b"),
)
app = FastAPI(title="RootSignal API", version="0.2.0")
LOGGER = logging.getLogger("rootsignal.api")
RATE_LIMITER = RateLimiter(
    limit=int(os.getenv("ROOTSIGNAL_RATE_LIMIT", "60")),
    window_seconds=float(os.getenv("ROOTSIGNAL_RATE_WINDOW_SECONDS", "60")),
)
RATE_LIMITED_PATHS = {
    "/v1/investigations",
    "/v1/knowledge",
    "/v1/baselines/deterministic",
    "/v1/comparisons",
    "/v1/incidents",
}


def _error(code: str, message: str, correlation_id: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "request_id": correlation_id}}


@app.middleware("http")
async def harden_http(request: Request, call_next):
    started = time.perf_counter()
    correlation_id = request_id(request.headers.get("x-request-id"))
    request.state.request_id = correlation_id
    if any(
        request.url.path == path or request.url.path.startswith(f"{path}/")
        for path in RATE_LIMITED_PATHS
    ):
        client = request.client.host if request.client else "unknown"
        allowed, remaining, retry_after = RATE_LIMITER.allow(f"{client}:{request.url.path}")
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content=_error("rate_limit_exceeded", "Too many requests", correlation_id),
                headers={"Retry-After": str(retry_after)},
            )
        else:
            response = await call_next(request)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
    else:
        response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    METRICS.record_http(
        request.method, request.url.path, response.status_code, time.perf_counter() - started
    )
    log_event(
        LOGGER,
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        request_id=correlation_id,
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    correlation_id = getattr(request.state, "request_id", request_id(None))
    codes = {
        404: "not_found",
        409: "comparison_conflict",
        422: "validation_error",
        429: "rate_limit_exceeded",
        503: "service_unavailable",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=_error(codes.get(exc.status_code, "request_failed"), str(exc.detail), correlation_id),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    correlation_id = getattr(request.state, "request_id", request_id(None))
    fields = sorted({".".join(str(part) for part in error["loc"][1:]) for error in exc.errors()})
    message = "Invalid request" + (f": {', '.join(fields)}" if fields else "")
    return JSONResponse(status_code=422, content=_error("validation_error", message, correlation_id))


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = getattr(request.state, "request_id", request_id(None))
    LOGGER.exception("Unhandled API error request_id=%s", correlation_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_error("internal_error", "Unexpected server error", correlation_id),
    )


class InvestigationRequest(BaseModel):
    incident_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    query: str | None = Field(default=None, min_length=3, max_length=2000)
    collection_ids: list[str] = Field(
        default_factory=lambda: ["incident-runbooks"], min_length=1, max_length=10
    )


class KnowledgeRequest(BaseModel):
    collection_id: str = Field(pattern=r"^[a-z0-9-]+$")
    source: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20, max_length=1_000_000)


class CollectionRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class ComparisonRequest(BaseModel):
    reference_run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    candidate_run_id: str = Field(pattern=r"^[a-f0-9]{32}$")


def _incident_path(incident_id: str) -> Path | None:
    paths = sorted([*FIXTURE_ROOT.glob("*.yaml"), *FIXTURE_ROOT.glob("*.json")])
    return next((path for path in paths if load_incident(path).incident_id == incident_id), None)


def _incident(incident_id: str) -> Incident | None:
    path = _incident_path(incident_id)
    return load_incident(path) if path else CUSTOM_INCIDENTS.get(incident_id)


def _public_incident(incident: Incident, *, include_observations: bool = False) -> dict[str, object]:
    telemetry = incident.telemetry
    counts = {
        "metrics": len(telemetry.get("metrics", {})),
        "logs": len(telemetry.get("logs", [])),
        "deployments": len(telemetry.get("deployments", [])),
        "runbooks": len(incident.runbooks),
    }
    public: dict[str, object] = {
        "id": incident.incident_id,
        "title": incident.title,
        "summary": incident.summary,
        "metadata": {
            **incident.metadata,
            "catalog_source": "custom" if CUSTOM_INCIDENTS.digest(incident.incident_id) else "built-in",
        },
        "observation_counts": counts,
    }
    if include_observations:
        public["telemetry"] = telemetry
        public["runbooks"] = incident.runbooks
    return public


def _incidents() -> list[Incident]:
    paths = sorted([*FIXTURE_ROOT.glob("*.yaml"), *FIXTURE_ROOT.glob("*.json")])
    return sorted(
        [*(load_incident(path) for path in paths), *CUSTOM_INCIDENTS.list()],
        key=lambda incident: incident.incident_id,
    )


def _record_result(
    *,
    incident: Incident,
    mode: ExecutionMode,
    query: str,
    result: dict[str, object],
    latency_ms: float,
    request_id_value: str,
) -> dict[str, object]:
    path = _incident_path(incident.incident_id)
    fixture_sha256 = (
        hashlib.sha256(path.read_bytes()).hexdigest()
        if path
        else CUSTOM_INCIDENTS.digest(incident.incident_id) or "unavailable"
    )
    run = result.get("run", {})
    run_metadata = run if isinstance(run, dict) else {}
    model = str(run_metadata.get("model", LLM.model if mode == "model" else "deterministic-v1"))
    metadata = {
        "api_version": app.version,
        "latency_ms": round(latency_ms, 3),
        "oracle_backed": mode == "baseline",
        "request_id": request_id_value,
        "retrieval_engine": "sqlite-fts5",
        "prompt_tokens": int(run_metadata.get("prompt_tokens", 0)),
        "completion_tokens": int(run_metadata.get("completion_tokens", 0)),
        "retrieved_chunks": int(run_metadata.get("retrieved_chunks", 0)),
    }
    reference = RUNS.save(
        incident_id=incident.incident_id,
        incident_title=incident.title,
        mode=mode,
        model=model,
        query=query,
        fixture_sha256=fixture_sha256,
        result=result,
        metadata=metadata,
    )
    result["record"] = reference
    return result


def _seed_knowledge() -> None:
    incidents = [
        *(load_incident(path) for path in [*FIXTURE_ROOT.glob("*.yaml"), *FIXTURE_ROOT.glob("*.json")]),
        *CUSTOM_INCIDENTS.list(),
    ]
    for incident in incidents:
        for runbook in incident.runbooks:
            KNOWLEDGE.ingest(f"runbook/{runbook.get('id', 'unknown')}", runbook.get("content", ""))


_seed_knowledge()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness():
    model_server = LLM.healthy()
    ready = FIXTURE_ROOT.exists() and model_server
    content = {
        "status": "ready" if ready else "not_ready",
        "model": LLM.model,
        "model_server": model_server,
        "knowledge": KNOWLEDGE.stats(),
    }
    if not ready:
        return JSONResponse(status_code=503, content=content)
    return content


@app.get("/v1/system")
def system() -> dict[str, object]:
    model_healthy = LLM.healthy()
    return {
        "llm": {
            "provider": "openai-compatible",
            "model": LLM.model,
            "healthy": model_healthy,
            "configuration": {
                "endpoint_env": "INCIDENTLAB_LLM_URL",
                "model_env": "INCIDENTLAB_MODEL",
            },
        },
        "execution_modes": {
            "baseline": {
                "available": FIXTURE_ROOT.exists(),
                "oracle_backed": True,
                "purpose": "Reproducible control run for pipeline verification",
            },
            "model": {
                "available": model_healthy,
                "oracle_backed": False,
                "purpose": "Grounded agent run for evaluation",
            },
        },
        "retrieval": {"engine": "sqlite-fts5", **KNOWLEDGE.stats()},
        "tools": ["query_metrics", "query_logs", "query_deployments", "search_runbooks"],
        "inference": {"development": "llama.cpp", "production": "openai-compatible/vllm"},
    }


@app.get("/v1/benchmarks/latest")
def latest_benchmark() -> dict[str, object]:
    if not BENCHMARK_PATH.exists():
        raise HTTPException(status_code=404, detail="No benchmark result published")
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


@app.get("/v1/incidents")
def incident_catalog() -> dict[str, object]:
    incidents = [_public_incident(incident) for incident in _incidents()]
    return {"schema_version": "1.0", "count": len(incidents), "incidents": incidents}


@app.post("/v1/incidents", status_code=201)
def create_incident(fixture: dict[str, object]) -> dict[str, object]:
    incident_id = str(fixture.get("id", ""))
    if _incident(incident_id) is not None:
        raise HTTPException(status_code=409, detail="Incident id already exists")
    try:
        reference = CUSTOM_INCIDENTS.save(fixture)
        incident = CUSTOM_INCIDENTS.get(incident_id)
        assert incident is not None
        for runbook in incident.runbooks:
            KNOWLEDGE.ingest(
                f"runbook/{runbook.get('id', 'unknown')}", runbook.get("content", "")
            )
        return {"incident": _public_incident(incident), "record": reference}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/incidents/{incident_id}")
def incident_detail(incident_id: str) -> dict[str, object]:
    incident = _incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    return _public_incident(incident, include_observations=True)


@app.get("/v1/runs")
def list_runs(limit: int = 20) -> dict[str, object]:
    runs = RUNS.list(limit)
    return {"count": len(runs), "runs": runs}


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")
    return run


@app.get("/v1/runs/{run_id}/export")
def export_run(run_id: str, compare_to: str | None = None) -> JSONResponse:
    run = RUNS.get(run_id)
    comparison_run = RUNS.get(compare_to) if compare_to else None
    if run is None or (compare_to and comparison_run is None):
        raise HTTPException(status_code=404, detail="Unknown run")
    incident = _incident(str(run["incident_id"]))
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident fixture unavailable")
    try:
        bundle = build_evidence_bundle(incident, run, comparison_run)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": f'attachment; filename="rootsignal-{run_id}.json"',
        },
    )


@app.post("/v1/comparisons")
def compare(payload: ComparisonRequest) -> dict[str, object]:
    if payload.reference_run_id == payload.candidate_run_id:
        raise HTTPException(status_code=409, detail="Select two different runs")
    reference = RUNS.get(payload.reference_run_id)
    candidate = RUNS.get(payload.candidate_run_id)
    if reference is None or candidate is None:
        raise HTTPException(status_code=404, detail="Unknown run")
    incident = _incident(str(reference["incident_id"]))
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident fixture unavailable")
    try:
        return compare_runs(incident, reference, candidate)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/knowledge")
def ingest_knowledge(request: KnowledgeRequest) -> dict[str, object]:
    try:
        return KNOWLEDGE.ingest(request.source, request.text, request.collection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/knowledge/collections")
def list_knowledge_collections() -> dict[str, object]:
    collections = KNOWLEDGE.list_collections()
    return {"count": len(collections), "collections": collections}


@app.post("/v1/knowledge/collections", status_code=201)
def create_knowledge_collection(request: CollectionRequest) -> dict[str, str]:
    try:
        return KNOWLEDGE.create_collection(request.id, request.name, request.description)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(METRICS.prometheus(), media_type="text/plain; version=0.0.4")


@app.post("/v1/investigations")
def investigate(payload: InvestigationRequest, request: Request) -> dict[str, object]:
    incident = _incident(payload.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    collections = payload.collection_ids
    known = {str(item["id"]) for item in KNOWLEDGE.list_collections()}
    if unknown := sorted(set(collections) - known):
        raise HTTPException(
            status_code=422,
            detail=f"Unknown knowledge collections: {unknown}",
        )
    query = payload.query or incident.summary
    started = time.perf_counter()
    with METRICS.investigation():
        try:
            with trace_span(
                "rootsignal.investigate",
                {"rootsignal.incident_id": incident.incident_id, "rootsignal.model": LLM.model},
            ):
                result = GroundedAgent(
                    KNOWLEDGE, LLM, collection_ids=collections
                ).investigate(query, incident)
            run = result.get("run", {})
            if isinstance(run, dict):
                METRICS.record_agent_run(run)
            log_event(
                LOGGER,
                "investigation_completed",
                incident_id=incident.incident_id,
                request_id=getattr(request.state, "request_id", "unknown"),
                run=run,
            )
            return _record_result(
                incident=incident,
                mode="model",
                query=query,
                result=result,
                latency_ms=(time.perf_counter() - started) * 1000,
                request_id_value=getattr(request.state, "request_id", "unknown"),
            )
        except Exception as exc:
            LOGGER.warning(
                "Model unavailable request_id=%s",
                getattr(request.state, "request_id", "unknown"),
                exc_info=exc,
            )
            raise HTTPException(status_code=503, detail="Local model unavailable") from exc


@app.post("/v1/baselines/deterministic")
def deterministic_baseline(payload: InvestigationRequest, request: Request) -> dict[str, object]:
    incident = _incident(payload.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    started = time.perf_counter()
    result = Investigator().investigate(incident).as_dict()
    return _record_result(
        incident=incident,
        mode="baseline",
        query=payload.query or incident.summary,
        result=result,
        latency_ms=(time.perf_counter() - started) * 1000,
        request_id_value=getattr(request.state, "request_id", "unknown"),
    )
