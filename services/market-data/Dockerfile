# Build context: services/   docker build -f services/market-data/Dockerfile services
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

COPY market-data/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY python-common /tmp/python-common
RUN pip install --no-cache-dir "/tmp/python-common[web]" && rm -rf /tmp/python-common

COPY market-data/ .

RUN useradd --system --uid 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
