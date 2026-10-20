"""FastAPI 서비스 공통 설정: 요청 추적 ID 전파, 접근 로그, /metrics, /health."""
import logging
import time
import uuid

from fastapi import FastAPI, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from myanalyst_common import observability


def create_app(title: str, service: str) -> FastAPI:
    app = FastAPI(title=title)
    logger = logging.getLogger(f"myanalyst.{service}")

    @app.middleware("http")
    async def trace_request(request, call_next):
        """Spring → FastAPI 호출에서 받은 X-Trace-Id를 그대로 이어 쓴다."""
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        observability.set_trace_id(trace_id)
        started_at = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            "request service=%s trace_id=%s method=%s path=%s status=%s latency_ms=%.1f",
            service, trace_id, request.method, request.url.path, response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return response

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(observability.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health", status_code=status.HTTP_200_OK)
    def health_check():
        return {"status": "ok", "service": service}

    return app
