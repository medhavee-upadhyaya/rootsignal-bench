FROM python:3.12.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY incidentlab ./incidentlab
COPY evals ./evals
COPY training ./training
COPY benchmarks ./benchmarks
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir '.[api,observability]'

FROM python:3.12.11-slim-bookworm AS runtime

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INCIDENTLAB_FIXTURES=/app/fixtures/incidents \
    INCIDENTLAB_DB=/data/incidentlab.db

RUN addgroup --system --gid 10001 rootsignal \
    && adduser --system --uid 10001 --ingroup rootsignal --home /nonexistent rootsignal \
    && mkdir -p /data \
    && chown rootsignal:rootsignal /data
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=rootsignal:rootsignal incidentlab ./incidentlab
COPY --chown=rootsignal:rootsignal fixtures ./fixtures
COPY --chown=rootsignal:rootsignal benchmarks/results ./benchmarks/results

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["uvicorn", "incidentlab.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
