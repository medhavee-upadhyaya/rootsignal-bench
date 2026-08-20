from __future__ import annotations

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
from .fixtures import load_incident
from .http import RateLimiter, request_id
from .knowledge import KnowledgeBase
from .llm import OllamaClient
from .observability import METRICS, log_event, trace_span
from .rag_agent import GroundedAgent

FIXTURE_ROOT = Path(os.getenv("INCIDENTLAB_FIXTURES", "fixtures/incidents")).resolve()
KNOWLEDGE = KnowledgeBase(os.getenv("INCIDENTLAB_DB", "work/incidentlab.db"))
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
RATE_LIMITED_PATHS = {"/v1/investigations", "/v1/knowledge", "/v1/baselines/deterministic"}


def _error(code: str, message: str, correlation_id: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "request_id": correlation_id}}


@app.middleware("http")
async def harden_http(request: Request, call_next):
    started = time.perf_counter()
    correlation_id = request_id(request.headers.get("x-request-id"))
    request.state.request_id = correlation_id
    if request.url.path in RATE_LIMITED_PATHS:
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
    codes = {404: "not_found", 429: "rate_limit_exceeded", 503: "service_unavailable"}
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
def investigate(payload: InvestigationRequest, request: Request) -> dict[str, object]:
    incident = _incident(payload.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    query = payload.query or incident.summary
    with METRICS.investigation():
        try:
            with trace_span(
                "rootsignal.investigate",
                {"rootsignal.incident_id": incident.incident_id, "rootsignal.model": LLM.model},
            ):
                result = GroundedAgent(KNOWLEDGE, LLM).investigate(query, incident)
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
            return result
        except Exception as exc:
            LOGGER.warning(
                "Model unavailable request_id=%s",
                getattr(request.state, "request_id", "unknown"),
                exc_info=exc,
            )
            raise HTTPException(status_code=503, detail="Local model unavailable") from exc


@app.post("/v1/baselines/deterministic")
def deterministic_baseline(request: InvestigationRequest) -> dict[str, object]:
    incident = _incident(request.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Unknown incident")
    return Investigator().investigate(incident).as_dict()
