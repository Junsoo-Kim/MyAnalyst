import contextvars
import logging
import time
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Counter, Histogram

logger = logging.getLogger("myanalyst.rag")

registry = CollectorRegistry()

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

STAGE_DURATION = Histogram(
    "rag_stage_duration_seconds",
    "Duration of a RAG pipeline stage",
    ["stage"],
    registry=registry,
)
MILVUS_SEARCH_DURATION = Histogram(
    "rag_milvus_search_duration_seconds",
    "Milvus collection search duration",
    ["collection"],
    registry=registry,
)
LLM_CALL_DURATION = Histogram(
    "rag_llm_call_duration_seconds",
    "LLM API call duration",
    ["model", "purpose"],
    registry=registry,
)
LLM_TOKENS_TOTAL = Counter(
    "rag_llm_tokens_total",
    "LLM tokens consumed",
    ["model", "purpose", "direction"],
    registry=registry,
)


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


def get_trace_id() -> str:
    return _trace_id.get()


@contextmanager
def time_stage(stage: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        STAGE_DURATION.labels(stage=stage).observe(elapsed)
        logger.info(
            "rag_stage trace_id=%s stage=%s latency_ms=%.1f",
            get_trace_id(), stage, elapsed * 1000,
        )


@contextmanager
def time_milvus_search(collection: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        MILVUS_SEARCH_DURATION.labels(collection=collection).observe(elapsed)
        logger.info(
            "rag_milvus_search trace_id=%s collection=%s latency_ms=%.1f",
            get_trace_id(), collection, elapsed * 1000,
        )


@contextmanager
def time_llm_call(model: str, purpose: str):
    started = time.perf_counter()
    usage = {}
    try:
        yield usage
    finally:
        elapsed = time.perf_counter() - started
        LLM_CALL_DURATION.labels(model=model, purpose=purpose).observe(elapsed)
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is not None:
            LLM_TOKENS_TOTAL.labels(model=model, purpose=purpose, direction="input").inc(prompt_tokens)
        if completion_tokens is not None:
            LLM_TOKENS_TOTAL.labels(model=model, purpose=purpose, direction="output").inc(completion_tokens)
        logger.info(
            "rag_llm_call trace_id=%s model=%s purpose=%s latency_ms=%.1f prompt_tokens=%s completion_tokens=%s",
            get_trace_id(), model, purpose, elapsed * 1000, prompt_tokens, completion_tokens,
        )


def record_usage(usage_holder: dict, response) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    usage_holder["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
    usage_holder["completion_tokens"] = getattr(usage, "completion_tokens", None)
