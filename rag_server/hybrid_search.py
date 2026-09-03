# hybrid_search.py
"""
하이브리드 검색: Milvus 기반 Dense(임베딩 코사인/L2) 검색과 BM25 기반 Sparse(키워드) 검색을
병렬로 수행하고, Reciprocal Rank Fusion(RRF)으로 병합한다.

왜 필요한가: 금융 도메인 텍스트는 숫자, 고유명사, 재무 식별자가 자연어와 섞여 있어
Dense 검색만으로는 정확한 키워드 일치를 놓치는 경우가 있다. BM25를 병행해 보완한다.

Milvus 2.4 standalone은 자체 BM25/Sparse 인덱스를 지원하지 않으므로, Sparse 인덱스는
여기서 rank_bm25로 별도 구축한다. 토크나이저는 새 의존성(KoNLPy 등, JDK 필요)을 늘리지
않기 위해 이미 로드돼 있는 KLUE-BERT WordPiece 토크나이저(utils.tokenizer)를 재사용한다 -
사람이 읽기엔 어색한 subword 토큰이지만, "질의와 문서를 같은 규칙으로 쪼갠다"는
BM25의 전제만 지키면 키워드 매칭 목적엔 충분하다.
"""
import time
from typing import Any, Dict, List

from pymilvus import Collection, utility
from rank_bm25 import BM25Okapi

import config
import utils

# 컬렉션 전체를 매 요청마다 다시 읽고 토크나이즈하면 느리므로, 프로세스 안에 캐싱한다.
# main.py의 FastAPI startup 이벤트가 서버 기동 시 한 번 미리 채워두고, 못 채웠으면
# 첫 검색 요청에서 지연 빌드(lazy build)로 재시도한다.
_bm25_state: Dict[str, Any] = {
    "index": None,   # BM25Okapi 인스턴스
    "chunks": [],     # index와 같은 순서로 대응되는 청크 메타데이터
}


def _tokenize(text: str) -> List[str]:
    """BM25용 토크나이저. 임베딩에 쓰는 KLUE-BERT 토크나이저를 재사용한다."""
    if not text:
        return []
    if utils.tokenizer is None:
        # 모델 초기화가 실패한 극단적인 경우의 최후 폴백
        return text.split()
    return utils.tokenizer.tokenize(text)


def build_bm25_index(force: bool = False) -> None:
    """Milvus 컬렉션 전체를 읽어 BM25 스파스 인덱스를 (재)구축한다."""
    if _bm25_state["index"] is not None and not force:
        return

    utils.ensure_milvus_connection()
    print("[BM25] Building sparse index from Milvus collections...")
    start = time.time()

    chunks: List[Dict[str, Any]] = []
    for c_name in config.COLLECTION_NAMES:
        if not utility.has_collection(c_name):
            print(f"  [BM25] Collection '{c_name}' does not exist. Skipping.")
            continue
        if c_name not in config.COLLECTION_FIELD_MAPPINGS:
            continue

        mapping = config.COLLECTION_FIELD_MAPPINGS[c_name]
        text_field = mapping["text_field"]
        output_fields = mapping["output_fields"]

        try:
            collection = Collection(c_name)
            if utility.load_state(c_name) != "Loaded":
                collection.load()
                utility.wait_for_loading_complete(c_name)

            query_fields = list(dict.fromkeys(["id", *output_fields]))  # 중복 제거, 순서 유지
            rows = collection.query(
                expr="id >= 0",
                output_fields=query_fields,
                limit=collection.num_entities,
            )
        except Exception as e:
            print(f"  [BM25] Error reading '{c_name}': {e}")
            continue

        for row in rows:
            text_value = row.get(text_field, "")
            if not text_value or not str(text_value).strip():
                continue
            chunk = {"collection": c_name, "id": row.get("id"), "text": text_value}
            for field in output_fields:
                if field != text_field and field in row:
                    chunk[field] = row[field]
            chunks.append(chunk)

    if not chunks:
        print("  [BM25] No documents found across collections. Sparse search will return empty.")
        _bm25_state["index"] = None
        _bm25_state["chunks"] = []
        return

    tokenized_corpus = [_tokenize(c["text"]) for c in chunks]
    _bm25_state["index"] = BM25Okapi(tokenized_corpus)
    _bm25_state["chunks"] = chunks

    print(f"  [BM25] Indexed {len(chunks)} chunks in {time.time() - start:.2f}s.")


def search_bm25(query: str, top_k: int) -> List[Dict[str, Any]]:
    """BM25 스파스 검색. Milvus dense 검색 결과와 같은 형태(dict: collection/id/text/score)로 반환한다."""
    build_bm25_index()  # 이미 빌드돼 있으면 즉시 반환(no-op)

    if _bm25_state["index"] is None:
        return []

    tokenized_query = _tokenize(query)
    if not tokenized_query:
        return []

    scores = _bm25_state["index"].get_scores(tokenized_query)
    chunks = _bm25_state["chunks"]

    ranked_indices = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:top_k]

    results = []
    for i in ranked_indices:
        if scores[i] <= 0:  # 매치가 전혀 없는 문서는 제외
            continue
        chunk = dict(chunks[i])
        chunk["score"] = float(scores[i])
        results.append(chunk)
    return results


def reciprocal_rank_fusion(
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    여러 검색기(dense/sparse)의 결과 리스트를 RRF로 병합한다.

    RRF가 유용한 이유: dense(L2 거리, 작을수록 좋음)와 sparse(BM25 score, 클수록 좋음)는
    스케일과 분포가 완전히 다르다. 두 점수를 직접 정규화해서 섞는 대신, 각 리스트 안에서의
    "순위(rank)"만 이용해 score = sum(1 / (k + rank + 1))로 합산한다 - 여러 검색기에서
    동시에 상위권에 오른 문서일수록 높은 점수를 받는다.
    """
    fused: Dict[Any, Dict[str, Any]] = {}

    for results in result_lists:
        for rank, item in enumerate(results):
            key = (item.get("collection"), item.get("id"))
            increment = 1.0 / (k + rank + 1)

            if key not in fused:
                fused[key] = dict(item)
                fused[key]["rrf_score"] = 0.0
            fused[key]["rrf_score"] += increment

    merged = list(fused.values())
    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    return merged


def hybrid_search(
    query_text: str,
    query_vector,
    collection_names: List[str],
    top_k: int,
) -> List[Dict[str, Any]]:
    """Dense(Milvus) + Sparse(BM25) 검색을 병행하고 RRF로 병합해 상위 top_k를 반환한다.

    config.HYBRID_SEARCH_ENABLED가 false이거나 BM25 인덱스가 비어있으면(코퍼스 없음 등)
    기존 dense-only 검색 결과를 그대로 반환한다 - 문제가 생겨도 이전 동작으로 안전하게 폴백.
    """
    dense_results = utils.search_milvus(query_vector, collection_names, config.SEARCH_TOP_K)

    if not config.HYBRID_SEARCH_ENABLED:
        return dense_results

    sparse_results = search_bm25(query_text, config.BM25_TOP_K)
    if not sparse_results:
        return dense_results

    fused = reciprocal_rank_fusion([dense_results, sparse_results], k=config.RRF_K)
    return fused[:top_k]
