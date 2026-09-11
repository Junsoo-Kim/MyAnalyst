import time
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch, helpers
from pymilvus import Collection, utility

import config
import utils

_opensearch_client: Optional[OpenSearch] = None


def _tokenize(text: str) -> List[str]:
    """OpenSearch의 기본(standard) 분석기는 한국어 조사·어미를 떼어내지 못한다
    ("영업이익은"과 "영업이익"을 다른 토큰으로 본다). KLUE-BERT WordPiece
    토크나이저로 색인·질의 양쪽을 똑같이 미리 나눠, `search_tokens` 필드에는
    이미 토큰화된 문자열만 whitespace 분석기로 넣는다."""
    if not text:
        return []
    if utils.tokenizer is None:
        return text.split()
    return utils.tokenizer.tokenize(text)


def get_opensearch_client() -> OpenSearch:
    global _opensearch_client
    if _opensearch_client is None:
        _opensearch_client = OpenSearch(
            hosts=[{"host": config.OPENSEARCH_HOST, "port": config.OPENSEARCH_PORT}],
            use_ssl=False,
            verify_certs=False,
        )
    return _opensearch_client


def _ensure_index(client: OpenSearch) -> None:
    if client.indices.exists(index=config.OPENSEARCH_INDEX):
        return
    client.indices.create(
        index=config.OPENSEARCH_INDEX,
        body={
            "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
            "mappings": {
                "properties": {
                    "collection": {"type": "keyword"},
                    "milvus_id": {"type": "keyword"},
                    "text": {"type": "text", "index": False},
                    "search_tokens": {"type": "text", "analyzer": "whitespace"},
                }
            },
        },
    )


def build_bm25_index(force: bool = False) -> None:
    """Milvus 컬렉션의 텍스트를 OpenSearch에 색인한다.

    인덱스는 Worker 프로세스가 아니라 OpenSearch가 들고 있으므로, 여러 Worker가
    같은 인덱스를 공유한다 — Worker 수만큼 메모리를 중복 소비하지 않는다. 이미
    문서가 있으면(다른 Worker가 먼저 색인했거나 이전 실행에서 남아 있으면)
    `force=True`가 아닌 한 다시 읽지 않는다.
    """
    client = get_opensearch_client()
    _ensure_index(client)

    if not force:
        count = client.count(index=config.OPENSEARCH_INDEX)["count"]
        if count > 0:
            return
        client.indices.refresh(index=config.OPENSEARCH_INDEX)
        count = client.count(index=config.OPENSEARCH_INDEX)["count"]
        if count > 0:
            return

    utils.ensure_milvus_connection()
    print("[BM25] Indexing Milvus collections into OpenSearch...")
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

            query_fields = list(dict.fromkeys(["id", *output_fields]))
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

    if force:
        client.delete_by_query(
            index=config.OPENSEARCH_INDEX, body={"query": {"match_all": {}}}
        )

    if not chunks:
        print("  [BM25] No documents found across collections. Sparse search will return empty.")
        return

    def actions():
        for chunk in chunks:
            source = dict(chunk)
            milvus_id = source.pop("id")
            source["milvus_id"] = milvus_id
            source["search_tokens"] = " ".join(_tokenize(str(chunk["text"])))
            yield {
                "_index": config.OPENSEARCH_INDEX,
                "_id": f"{chunk['collection']}:{milvus_id}",
                "_source": source,
            }

    helpers.bulk(client, actions())
    client.indices.refresh(index=config.OPENSEARCH_INDEX)

    print(f"  [BM25] Indexed {len(chunks)} chunks into OpenSearch in {time.time() - start:.2f}s.")


def search_bm25(query: str, top_k: int) -> List[Dict[str, Any]]:
    build_bm25_index()

    query_tokens = " ".join(_tokenize(query))
    if not query_tokens:
        return []

    client = get_opensearch_client()
    response = client.search(
        index=config.OPENSEARCH_INDEX,
        body={
            "size": top_k,
            "query": {"match": {"search_tokens": {"query": query_tokens}}},
        },
    )

    results = []
    for hit in response["hits"]["hits"]:
        chunk = dict(hit["_source"])
        chunk.pop("search_tokens", None)
        chunk["id"] = chunk.pop("milvus_id", None)
        chunk["score"] = float(hit["_score"])
        results.append(chunk)
    return results

def reciprocal_rank_fusion(
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60,
) -> List[Dict[str, Any]]:
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
    dense_results = utils.search_milvus(query_vector, collection_names, config.SEARCH_TOP_K)

    if not config.HYBRID_SEARCH_ENABLED:
        return dense_results

    sparse_results = search_bm25(query_text, config.BM25_TOP_K)
    if not sparse_results:
        return dense_results

    fused = reciprocal_rank_fusion([dense_results, sparse_results], k=config.RRF_K)
    return fused[:top_k]
