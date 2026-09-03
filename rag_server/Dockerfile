FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# HuggingFace 캐시를 /app 아래로 고정해, 비루트 사용자(raguser)로도 접근 가능하게 합니다.
ENV HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
# torch는 CPU 전용 wheel을 받아 이미지 크기/빌드 시간을 크게 줄입니다.
# (이 서비스는 GPU 인스턴스를 쓰지 않는 전제 - utils.py는 cuda 미탐지 시 자동으로 cpu를 사용합니다)
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# 임베딩 모델 가중치를 빌드 타임에 미리 받아 이미지에 포함시켜,
# 컨테이너 기동 시 HuggingFace Hub 접근 실패로 서비스가 죽는 것을 방지합니다.
RUN python -c "from transformers import AutoTokenizer, AutoModel; \
AutoTokenizer.from_pretrained('klue/bert-base'); \
AutoModel.from_pretrained('klue/bert-base')"

COPY . .

RUN useradd --system --uid 1001 raguser \
    && mkdir -p /app/logs \
    && chown -R raguser:raguser /app
USER raguser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
