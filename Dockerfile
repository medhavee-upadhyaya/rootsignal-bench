FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN addgroup --system incidentlab && adduser --system --ingroup incidentlab incidentlab
WORKDIR /app
COPY pyproject.toml README.md ./
COPY incidentlab ./incidentlab
COPY evals ./evals
COPY training ./training
COPY benchmarks ./benchmarks
COPY fixtures ./fixtures
RUN pip install --no-cache-dir '.[api,observability]'
USER incidentlab
EXPOSE 8000
CMD ["uvicorn", "incidentlab.api:app", "--host", "0.0.0.0", "--port", "8000"]
