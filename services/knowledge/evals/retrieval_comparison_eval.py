"""BM25 토큰화와 하이브리드 검색의 효과를 같은 문서·같은 질의로 비교한다(OpenAI 호출 없음).

  docker compose up -d --wait etcd minio milvus opensearch
  docker compose run --rm --no-deps -v ./services/knowledge:/src -e PYTHONPATH=/src -w /src \
      knowledge python -m evals.retrieval_comparison_eval

데이터: evals/data/corpus.local.jsonl(build_retrieval_dataset.py로 생성), evals/data/queries.jsonl.
운영 인덱스는 건드리지 않는다. 평가용 Milvus 컬렉션과 OpenSearch 인덱스를 따로 만들고 끝나면 지운다.

비교하는 설정(모두 top 20을 가져와 상위 10개로 평가):
  dense           KLUE-BERT 임베딩 + Milvus(FLAT, L2)
  bm25_standard   OpenSearch 기본(standard) 분석기로 원문 색인·질의          ← 토큰화 수정 전
  bm25_wordpiece  KLUE-BERT WordPiece로 미리 토큰화(hybrid_search._tokenize) ← 현재 운영 방식
  hybrid_standard dense + bm25_standard, RRF
  hybrid          dense + bm25_wordpiece, RRF                               ← 현재 운영 방식
"""
import contextlib
import io
import json
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

warnings.filterwarnings("ignore")

with contextlib.redirect_stdout(io.StringIO()):
    from opensearchpy import helpers
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

    import config
    import embedding
    import hybrid_search
    import milvus_store
    from evals import retrieval_dataset as ds
    from evaluation import metrics

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "data" / "corpus.local.jsonl"
QUERIES = HERE / "data" / "queries.jsonl"
RESULTS = HERE / "results" / "retrieval_comparison.json"

COLLECTION = "eval_retrieval_comparison"
INDEX_STANDARD = "eval-retrieval-standard"
INDEX_WORDPIECE = "eval-retrieval-wordpiece"
FETCH_K = config.SEARCH_TOP_K
EVAL_K = 10
CONFIGS = ["dense", "bm25_standard", "bm25_wordpiece", "hybrid_standard", "hybrid"]


def load_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_chunks(corpus: List[dict]) -> List[dict]:
    chunks = []
    for article in corpus:
        for index, text in enumerate(ds.chunk_article(article["body"])):
            chunks.append({"key": f"{article['id']}:{index}", "article_id": article["id"], "text": text})
    return chunks


def index_dense(chunks: List[dict]) -> Collection:
    milvus_store.ensure_milvus_connection()
    if utility.has_collection(COLLECTION):
        utility.drop_collection(COLLECTION)
    schema = CollectionSchema([
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=config.VECTOR_DIM),
        FieldSchema(name="chunk_key", dtype=DataType.VARCHAR, max_length=64),
    ])
    collection = Collection(COLLECTION, schema=schema)
    collection.create_index("embedding", {"index_type": "FLAT", "metric_type": "L2", "params": {}})
    vectors = [embedding.get_embedding(c["text"]).tolist() for c in chunks]
    collection.insert([list(range(len(chunks))), vectors, [c["key"] for c in chunks]])
    collection.flush()
    collection.load()
    return collection


def index_sparse(chunks: List[dict]) -> None:
    client = hybrid_search.get_opensearch_client()
    for name, mapping in (
        (INDEX_STANDARD, {"text": {"type": "text", "analyzer": "standard"}}),
        (INDEX_WORDPIECE, {"search_tokens": {"type": "text", "analyzer": "whitespace"}}),
    ):
        if client.indices.exists(index=name):
            client.indices.delete(index=name)
        client.indices.create(index=name, body={
            "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
            "mappings": {"properties": {"chunk_key": {"type": "keyword"}, **mapping}},
        })
    helpers.bulk(client, (
        {"_index": INDEX_STANDARD, "_id": c["key"], "_source": {"chunk_key": c["key"], "text": c["text"]}}
        for c in chunks))
    helpers.bulk(client, (
        {"_index": INDEX_WORDPIECE, "_id": c["key"],
         "_source": {"chunk_key": c["key"], "search_tokens": " ".join(hybrid_search._tokenize(c["text"]))}}
        for c in chunks))
    client.indices.refresh(index=f"{INDEX_STANDARD},{INDEX_WORDPIECE}")


def search_dense(collection: Collection, query: str) -> List[str]:
    vector = embedding.get_embedding(query)
    hits = collection.search([vector.tolist()], "embedding", {"metric_type": "L2", "params": {}},
                             limit=FETCH_K, output_fields=["chunk_key"])[0]
    return [hit.entity.get("chunk_key") for hit in hits]


def search_sparse(index: str, query: str) -> List[str]:
    client = hybrid_search.get_opensearch_client()
    if index == INDEX_STANDARD:
        body = {"size": FETCH_K, "query": {"match": {"text": query}}}
    else:
        body = {"size": FETCH_K, "query": {"match": {"search_tokens": " ".join(hybrid_search._tokenize(query))}}}
    return [hit["_source"]["chunk_key"] for hit in client.search(index=index, body=body)["hits"]["hits"]]


def rrf(*rankings: List[str]) -> List[str]:
    # 운영 코드의 RRF를 그대로 쓴다(키는 (collection, id)).
    lists = [[{"collection": "eval", "id": key} for key in ranking] for ranking in rankings]
    return [item["id"] for item in hybrid_search.reciprocal_rank_fusion(lists, k=config.RRF_K)]


def run_query(collection: Collection, query: str) -> Dict[str, List[str]]:
    dense = search_dense(collection, query)
    standard = search_sparse(INDEX_STANDARD, query)
    wordpiece = search_sparse(INDEX_WORDPIECE, query)
    return {
        "dense": dense,
        "bm25_standard": standard,
        "bm25_wordpiece": wordpiece,
        "hybrid_standard": rrf(dense, standard),
        "hybrid": rrf(dense, wordpiece),
    }


def summarize(rows: List[dict]) -> Dict[str, Dict[str, float]]:
    out = {}
    for name in CONFIGS:
        # 정답이 여러 청크일 수 있으므로(같은 문장을 실은 다른 매체) Hit@k는 "정답 중 하나라도 상위 k에 있는가"다.
        hit1 = [float(bool(set(r["rankings"][name][:1]) & set(r["relevant"]))) for r in rows]
        hit10 = [float(bool(set(r["rankings"][name][:EVAL_K]) & set(r["relevant"]))) for r in rows]
        mrr = [metrics.reciprocal_rank(r["rankings"][name][:EVAL_K], r["relevant"]) for r in rows]
        n = max(1, len(rows))
        out[name] = {"hit@1": sum(hit1) / n, "hit@10": sum(hit10) / n, "mrr@10": sum(mrr) / n,
                     "miss@10": 1 - sum(hit10) / n}
    return out


def print_table(title: str, summary: Dict[str, Dict[str, float]], n: int) -> None:
    print(f"\n  {title} (질의 {n}개)")
    print(f"  {'설정':<17}{'Hit@1':>8}{'Hit@10':>8}{'MRR@10':>8}{'Miss@10':>9}")
    for name in CONFIGS:
        s = summary[name]
        print(f"  {name:<17}{s['hit@1']:>8.3f}{s['hit@10']:>8.3f}{s['mrr@10']:>8.3f}{s['miss@10']:>9.3f}")


def main() -> None:
    corpus = {a["id"]: a for a in load_jsonl(CORPUS)}
    queries = load_jsonl(QUERIES)
    chunks = build_chunks(list(corpus.values()))
    print(f"articles {len(corpus)}, chunks {len(chunks)}, query sentences {len(queries)}")

    start = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        collection = index_dense(chunks)
        index_sparse(chunks)
    print(f"indexed in {time.time() - start:.1f}s (Milvus '{COLLECTION}', OpenSearch '{INDEX_STANDARD}', '{INDEX_WORDPIECE}')")

    rows, skipped = [], 0
    try:
        for q in queries:
            relevant = ds.relevant_chunk_keys(corpus, q["article_id"], q["sentence_sha1"])
            if not relevant:
                skipped += 1
                continue
            for query_type in ("verbatim", "keyword"):
                with contextlib.redirect_stdout(io.StringIO()):
                    rankings = run_query(collection, q[query_type])
                rows.append({"id": q["id"], "type": query_type, "query": q[query_type],
                             "has_number": ds.query_has_number(q), "relevant": relevant,
                             "rankings": {k: v[:EVAL_K] for k, v in rankings.items()}})
    finally:
        with contextlib.redirect_stdout(io.StringIO()):
            utility.drop_collection(COLLECTION)
            client = hybrid_search.get_opensearch_client()
            client.indices.delete(index=f"{INDEX_STANDARD},{INDEX_WORDPIECE}", ignore_unavailable=True)

    groups = defaultdict(list)
    for row in rows:
        groups[row["type"]].append(row)
        if row["type"] == "keyword":
            groups["keyword_with_number" if row["has_number"] else "keyword_without_number"].append(row)

    report = {
        "dataset": {"articles": len(corpus), "chunks": len(chunks), "query_sentences": len(queries) - skipped,
                    "skipped_sentences": skipped,
                    "multi_relevant_queries": sum(1 for r in rows if r["type"] == "keyword" and len(r["relevant"]) > 1), "fetch_k": FETCH_K, "eval_k": EVAL_K, "rrf_k": config.RRF_K,
                    "embedding_model": config.EMBEDDING_MODEL_NAME},
        "summary": {name: summarize(group) for name, group in groups.items()},
        "counts": {name: len(group) for name, group in groups.items()},
        "per_query": [{k: v for k, v in r.items()} for r in rows],
    }
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    bar = "=" * 58
    print(f"\n{bar}\n  검색 설정 비교 (정답 = 질의를 만든 문장이 들어 있는 청크)\n{bar}")
    for name, title in (("verbatim", "verbatim: 문장 어절 그대로"), ("keyword", "keyword: 조사 제거 명사 위주"),
                        ("keyword_with_number", "keyword 중 숫자 포함"),
                        ("keyword_without_number", "keyword 중 숫자 없음")):
        if name in groups:
            print_table(title, report["summary"][name], len(groups[name]))
    print(f"\n  skipped sentences (article changed): {skipped}")
    print(f"  results: {RESULTS.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
