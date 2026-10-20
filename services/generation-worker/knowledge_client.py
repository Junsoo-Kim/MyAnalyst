# knowledge_client.py — knowledge-service 검색 API 클라이언트
from typing import Any, Dict, List, Optional

import requests

import config
from myanalyst_common import observability


class KnowledgeServiceError(RuntimeError):
    """검색 서비스에 닿지 못했다. 빈 컨텍스트로 보고서를 만들지 않고 이번 시도를 실패시켜 재시도받는다."""


# 평가 스크립트가 임시 컬렉션으로 검색하도록 바꿀 때만 쓴다. None이면 knowledge-service 기본 컬렉션.
COLLECTIONS_OVERRIDE: Optional[List[str]] = None


def search(query: str, top_k: int = config.SEARCH_TOP_K) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {"query": query, "top_k": top_k}
    if COLLECTIONS_OVERRIDE:
        payload["collections"] = COLLECTIONS_OVERRIDE
    try:
        response = requests.post(
            f"{config.KNOWLEDGE_SERVICE_URL}/search",
            json=payload,
            headers={"X-Trace-Id": observability.get_trace_id()},
            timeout=config.KNOWLEDGE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise KnowledgeServiceError(f"knowledge-service 검색 실패: {e}") from e
    return response.json()["results"]
