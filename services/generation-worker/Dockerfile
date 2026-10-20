# Build context: services/   docker build -f services/generation-worker/Dockerfile services
# No torch / embedding model here: retrieval is delegated to knowledge-service over HTTP.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    SECTION_CHECKPOINT_DB_PATH=/app/data/section_checkpoints.sqlite3

COPY generation-worker/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY python-common /tmp/python-common
RUN pip install --no-cache-dir "/tmp/python-common[llm]" && rm -rf /tmp/python-common

COPY generation-worker/ .

RUN useradd --system --uid 1001 appuser \
    && mkdir -p /app/logs /app/data \
    && chown -R appuser:appuser /app
USER appuser

# Prometheus metrics (worker_jobs_total, worker_rebalances_total, rag_llm_* ...)
EXPOSE 9100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9100/metrics', timeout=3)" || exit 1

CMD ["python", "worker.py"]
