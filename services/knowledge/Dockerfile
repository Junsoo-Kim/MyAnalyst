# Build context: services/  (shares python-common with the other Python services)
#   docker build -f services/knowledge/Dockerfile services
# The same image runs the search API (default CMD) and the ingest batch (python ingest.py ...).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1

COPY knowledge/requirements.txt ./
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY python-common /tmp/python-common
RUN pip install --no-cache-dir "/tmp/python-common[web]" && rm -rf /tmp/python-common

RUN python -c "from transformers import AutoTokenizer, AutoModel; \
AutoTokenizer.from_pretrained('klue/bert-base'); \
AutoModel.from_pretrained('klue/bert-base')"

COPY knowledge/ .

RUN useradd --system --uid 1001 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
