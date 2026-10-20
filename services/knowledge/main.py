# main.py — knowledge-service: 하이브리드 검색 API. Milvus·OpenSearch를 소유하고 읽기만 한다.
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import config
import embedding
import hybrid_search
import milvus_store
from myanalyst_common import observability
from myanalyst_common.web import create_app

app = create_app(title="MyAnalyst Knowledge Service", service="knowledge")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="검색 질의(보통 LLM이 만든 섹션별 키워드)")
    top_k: int = Field(default=config.SEARCH_TOP_K, ge=1, le=100)
    collections: Optional[List[str]] = Field(
        default=None, description="생략하면 기본 컬렉션. 평가 스크립트가 임시 컬렉션을 지정할 때 쓴다.")


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]


@app.on_event("startup")
async def warm_up():
    # 모델 로딩(수 초)과 Milvus 연결을 첫 요청이 아니라 기동 시점에 치른다.
    embedding.initialize_models()
    try:
        milvus_store.ensure_milvus_connection()
    except RuntimeError as e:
        print(f"[WARN] Milvus 연결 실패 (첫 검색 요청 시 재시도): {e}")


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Dense(Milvus) + BM25(OpenSearch)를 RRF로 합친 결과를 돌려준다. 결과 항목 형식은
    생성 워커의 컨텍스트 포맷터가 기대하는 dict 그대로다(collection, id, text, 메타데이터, 점수)."""
    try:
        with observability.time_stage("hybrid_search"):
            results = await run_in_threadpool(
                hybrid_search.search, request.query, request.top_k, request.collections)
        return SearchResponse(results=results)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
