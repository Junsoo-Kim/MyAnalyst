import time
from typing import Any, Dict, List

from pymilvus import Collection, utility
from rank_bm25 import BM25Okapi

import config
import utils

_bm25_state: Dict[str, Any] = {
    "index": None,
    "chunks": [],
}

def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    if utils.tokenizer is None:
        return text.split()
    return utils.tokenizer.tokenize(text)

def build_bm25_index(force: bool = False) -> None:
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
    build_bm25_index()

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
        if scores[i] <= 0:
            continue
        chunk = dict(chunks[i])
        chunk["score"] = float(scores[i])
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
