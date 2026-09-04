import contextlib
import io
import math
import os
import re
import sys
import time
import warnings
from collections import Counter
from typing import Dict, List

warnings.filterwarnings("ignore")

with contextlib.redirect_stdout(io.StringIO()):
    import pandas as pd
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

    import config
    import hybrid_search
    import utils

CSV_PATH = "/data/processing/naver_news_data.csv"
EVAL_COLLECTION = "news_embeddings_eval"
TOP_K = 10
QUERY_KEYWORD_COUNT = 5
CHUNK_TARGET_LEN = 350

@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield

def chunk_text(text: str, target_len: int = CHUNK_TARGET_LEN) -> List[str]:
    sentences = re.split(r"(?<=[.!?다요])\s+", text.strip())
    chunks, current = [], ""
    for sent in sentences:
        if current and len(current) + len(sent) > target_len:
            chunks.append(current.strip())
            current = sent
        else:
            current = f"{current} {sent}".strip()
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 20]

def tokenize_ko(text: str) -> List[str]:
    return [t for t in re.findall(r"[가-힣A-Za-z0-9]+", text) if len(t) > 1]

def build_corpus(df: pd.DataFrame) -> List[Dict]:
    records = []
    for article_id, row in df.iterrows():
        for seq, chunk in enumerate(chunk_text(str(row["content"]))):
            records.append({
                "original_article_id": int(article_id),
                "chunk_seq_id": seq,
                "chunk_text": chunk,
                "title": str(row["title"])[:200],
                "datetime": str(row["datetime"])[:50],
                "summary": str(row["summary"])[:1000],
                "url": str(row["url"])[:500],
            })
    return records

def extract_query_keywords(df: pd.DataFrame, top_n: int = QUERY_KEYWORD_COUNT) -> Dict[int, str]:
    tokenized = [tokenize_ko(str(c)) for c in df["content"]]
    n_docs = len(tokenized)

    doc_freq = Counter()
    for tokens in tokenized:
        doc_freq.update(set(tokens))

    queries = {}
    for article_id, tokens in enumerate(tokenized):
        term_freq = Counter(tokens)
        scores = {
            term: tf * math.log(n_docs / (1 + doc_freq[term]))
            for term, tf in term_freq.items()
        }
        top_terms = [t for t, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]]
        queries[article_id] = " ".join(top_terms)
    return queries

def setup_eval_collection(records: List[Dict]) -> None:
    utils.ensure_milvus_connection()
    if utility.has_collection(EVAL_COLLECTION):
        utility.drop_collection(EVAL_COLLECTION)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=config.VECTOR_DIM),
        FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="original_article_id", dtype=DataType.INT64),
        FieldSchema(name="chunk_seq_id", dtype=DataType.INT64),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="datetime", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=1000),
    ]
    with quiet():
        collection = Collection(EVAL_COLLECTION, schema=CollectionSchema(fields=fields))
        collection.create_index("embedding", {"index_type": "FLAT", "metric_type": "L2", "params": {}})

    print(f"[1/3] Embedding {len(records)} chunks with KLUE-BERT (local, no API cost)...")
    start = time.time()
    batch_embeddings, batch_texts, batch_meta = [], [], []
    BATCH = 32

    def flush():
        if not batch_texts:
            return
        with quiet():
            collection.insert([
                batch_embeddings,
                batch_texts,
                [m["original_article_id"] for m in batch_meta],
                [m["chunk_seq_id"] for m in batch_meta],
                [m["title"] for m in batch_meta],
                [m["datetime"] for m in batch_meta],
                [m["summary"] for m in batch_meta],
                [m["url"] for m in batch_meta],
            ])
        batch_embeddings.clear()
        batch_texts.clear()
        batch_meta.clear()

    for i, rec in enumerate(records):
        emb = utils.get_embedding(rec["chunk_text"])
        if emb is None:
            continue
        batch_embeddings.append(emb.tolist())
        batch_texts.append(rec["chunk_text"])
        batch_meta.append(rec)
        if len(batch_texts) >= BATCH:
            flush()
        if (i + 1) % 100 == 0 or (i + 1) == len(records):
            print(f"      {i + 1}/{len(records)} embedded...", end="\r" if (i + 1) != len(records) else "\n")
    flush()

    with quiet():
        collection.flush()
        collection.load()
    print(f"      done in {time.time() - start:.1f}s ({collection.num_entities} chunks indexed).")

    config.COLLECTION_FIELD_MAPPINGS[EVAL_COLLECTION] = {
        "text_field": "chunk_text",
        "output_fields": ["chunk_text", "original_article_id", "chunk_seq_id", "title", "datetime", "summary", "url"],
    }

def evaluate(df: pd.DataFrame, queries: Dict[int, str]) -> Dict[str, float]:
    print(f"[2/3] Building BM25 sparse index for the eval collection...")
    original_collection_names = config.COLLECTION_NAMES
    config.COLLECTION_NAMES = [EVAL_COLLECTION]
    with quiet():
        hybrid_search.build_bm25_index(force=True)
    config.COLLECTION_NAMES = original_collection_names

    dense_hits, dense_recalls = [], []
    hybrid_hits, hybrid_recalls = [], []

    relevant_counts = Counter()
    for article_id, row in df.iterrows():
        relevant_counts[article_id] = len(chunk_text(str(row["content"])))

    print(f"[3/3] Running {len(queries)} queries through Dense-only and Hybrid search...")
    query_items = [(a, q) for a, q in queries.items() if q.strip() and relevant_counts[a] > 0]

    for i, (article_id, query) in enumerate(query_items):
        with quiet():
            qvec = utils.get_embedding(query)
            if qvec is None:
                continue
            dense_results = utils.search_milvus(qvec, [EVAL_COLLECTION], TOP_K)
            hybrid_results = hybrid_search.hybrid_search(
                query_text=query, query_vector=qvec, collection_names=[EVAL_COLLECTION], top_k=TOP_K,
            )

        def score(results):
            found = sum(1 for r in results if r.get("original_article_id") == article_id)
            hit = 1 if found > 0 else 0
            recall = min(found, relevant_counts[article_id]) / relevant_counts[article_id]
            return hit, recall

        dh, dr = score(dense_results)
        hh, hr = score(hybrid_results)
        dense_hits.append(dh)
        dense_recalls.append(dr)
        hybrid_hits.append(hh)
        hybrid_recalls.append(hr)

        if (i + 1) % 20 == 0 or (i + 1) == len(query_items):
            print(f"      {i + 1}/{len(query_items)} queries done...", end="\r" if (i + 1) != len(query_items) else "\n")

    n = len(dense_hits)
    return {
        "n": n,
        "dense_hit": sum(dense_hits) / n,
        "dense_recall": sum(dense_recalls) / n,
        "hybrid_hit": sum(hybrid_hits) / n,
        "hybrid_recall": sum(hybrid_recalls) / n,
    }

def print_report(result: Dict[str, float]) -> None:
    n, k = result["n"], TOP_K
    bar = "=" * 62
    print(f"\n{bar}")
    print(f"  하이브리드 검색(Dense+BM25+RRF) vs Dense-only  |  질의 {n}개, top_k={k}")
    print(f"  데이터: processing/naver_news_data.csv (실제 뉴스 {n}건 기반)")
    print(bar)
    print(f"  {'지표':<16}{'Dense-only':>14}{'Hybrid(RRF)':>14}{'개선폭':>12}")
    print(f"  {'-'*16}{'-'*14:>14}{'-'*14:>14}{'-'*12:>12}")
    for label, dkey, hkey in [
        (f"Hit@{k}", "dense_hit", "hybrid_hit"),
        (f"Recall@{k}", "dense_recall", "hybrid_recall"),
    ]:
        d, h = result[dkey], result[hkey]
        delta = h - d
        print(f"  {label:<16}{d:>14.4f}{h:>14.4f}{delta:>+12.4f}")
    print(bar)
    print("  Hit@K   = 정답 기사의 청크가 top-K에 하나라도 포함된 질의 비율")
    print("  Recall@K = 정답 기사가 가진 청크 중 top-K에 포함된 평균 비율")
    print(bar)

def cleanup():
    with quiet():
        utils.ensure_milvus_connection()
        if utility.has_collection(EVAL_COLLECTION):
            utility.drop_collection(EVAL_COLLECTION)
    config.COLLECTION_FIELD_MAPPINGS.pop(EVAL_COLLECTION, None)
    print(f"\n[cleanup] Dropped temporary collection '{EVAL_COLLECTION}'.")

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print(f"오류: {CSV_PATH} 를 찾을 수 없습니다.")
        print("docker-compose.yml에서 rag-server에 ./processing:/data/processing:ro 볼륨이")
        print("마운트되어 있는지 확인하세요 (run-hybrid-search-eval.bat 사용을 권장).")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} real articles from naver_news_data.csv")

    records = build_corpus(df)
    print(f"Chunked into {len(records)} chunks (avg {len(records)/len(df):.1f} chunks/article)\n")

    setup_eval_collection(records)
    queries = extract_query_keywords(df)

    try:
        result = evaluate(df, queries)
        print_report(result)
    finally:
        cleanup()
