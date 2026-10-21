"""BM25 토큰화, 임베딩 모델, 하이브리드 결합 방식의 효과를 같은 문서·같은 질의로 비교한다(OpenAI 호출 없음).

  docker compose up -d --wait etcd minio milvus opensearch
  docker compose run --rm --no-deps -v ./services/knowledge:/src -v hfcache:/hfcache -e PYTHONPATH=/src -w /src \
      knowledge python -m evals.retrieval_comparison_eval

데이터: evals/data/corpus.local.jsonl(build_retrieval_dataset.py로 생성), queries.jsonl, paraphrases.jsonl.
운영 인덱스는 건드리지 않는다. 평가용 Milvus 컬렉션과 OpenSearch 인덱스를 따로 만들고 끝나면 지운다.

질의 유형(같은 정답 문장에서 만든 세 가지):
  verbatim    문장 어절 그대로 앞 5개
  keyword     조사를 떼고 명사 위주 5개 (생성 파이프라인의 LLM 키워드와 같은 모양)
  paraphrase  원문 단어를 피해 다른 말로 쓴 질문 (paraphrases.jsonl, 사람이 작성)

설정(검색기마다 상위 20개를 가져온다. 하이브리드는 RRF로 합친 뒤 상위 20개):
  dense_klue         klue/bert-base 평균 풀링 + L2 (현재 운영 임베딩)
  dense_ko           jhgan/ko-sroberta-multitask(한국어 문장 임베딩) 평균 풀링 + 코사인
  bm25_standard      OpenSearch 기본 분석기 (토큰화 수정 전)
  bm25_wordpiece     KLUE-BERT WordPiece 사전 토큰화 (현재 운영)
  hybrid             dense_klue + bm25_wordpiece, RRF 1:1 (현재 운영)
  hybrid_bm25x2      dense_klue + bm25_wordpiece, RRF 1:2 (BM25 가중)
  hybrid_ko          dense_ko + bm25_wordpiece, RRF 1:1
  hybrid_ko_bm25x2   dense_ko + bm25_wordpiece, RRF 1:2
"""
import contextlib
import io
import json
import os
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

warnings.filterwarnings("ignore")

with contextlib.redirect_stdout(io.StringIO()):
    import torch
    from opensearchpy import helpers
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility
    from transformers import AutoModel, AutoTokenizer

    import config
    import embedding
    import hybrid_search
    import milvus_store
    from evals import retrieval_dataset as ds
    from evaluation import metrics

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "data" / "corpus.local.jsonl"
QUERIES = HERE / "data" / "queries.jsonl"
PARAPHRASES = HERE / "data" / "paraphrases.jsonl"
RESULTS = HERE / "results" / "retrieval_comparison.json"

KO_MODEL = os.getenv("EVAL_KO_EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
HF_CACHE = os.getenv("EVAL_HF_CACHE", "/hfcache")
COLLECTION_KLUE = "eval_retrieval_klue"
COLLECTION_KO = "eval_retrieval_ko"
INDEX_STANDARD = "eval-retrieval-standard"
INDEX_WORDPIECE = "eval-retrieval-wordpiece"
FETCH_K = config.SEARCH_TOP_K  # 20: 생성 파이프라인이 검색 결과를 받아 LLM 채점에 넘기는 후보 수
QUERY_TYPES = ["verbatim", "keyword", "paraphrase"]
CONFIGS = ["dense_klue", "dense_ko", "bm25_standard", "bm25_wordpiece",
           "hybrid", "hybrid_bm25x2", "hybrid_ko", "hybrid_ko_bm25x2"]


def load_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class KoEmbedder:
    """sentence-transformers 없이 같은 방식(평균 풀링 + 정규화)으로 문장 임베딩을 만든다."""

    def __init__(self, name: str):
        self.tokenizer = AutoTokenizer.from_pretrained(name, cache_dir=HF_CACHE)
        self.model = AutoModel.from_pretrained(name, cache_dir=HF_CACHE).eval()

    def __call__(self, text: str) -> List[float]:
        encoded = self.tokenizer(text, truncation=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            output = self.model(**encoded).last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1).float()
        vector = (output * mask).sum(1) / mask.sum(1)
        return torch.nn.functional.normalize(vector, dim=1)[0].tolist()


def build_chunks(corpus: List[dict]) -> List[dict]:
    chunks = []
    for article in corpus:
        for index, text in enumerate(ds.chunk_article(article["body"])):
            chunks.append({"key": f"{article['id']}:{index}", "text": text})
    return chunks


def index_dense(name: str, dim: int, metric: str, vectors: List[List[float]], keys: List[str]) -> Collection:
    if utility.has_collection(name):
        utility.drop_collection(name)
    collection = Collection(name, schema=CollectionSchema([
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="chunk_key", dtype=DataType.VARCHAR, max_length=64),
    ]))
    collection.create_index("embedding", {"index_type": "FLAT", "metric_type": metric, "params": {}})
    collection.insert([list(range(len(keys))), vectors, keys])
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


def search_dense(collection: Collection, vector: List[float], metric: str) -> List[str]:
    hits = collection.search([vector], "embedding", {"metric_type": metric, "params": {}},
                             limit=FETCH_K, output_fields=["chunk_key"])[0]
    return [hit.entity.get("chunk_key") for hit in hits]


def search_sparse(index: str, query: str) -> List[str]:
    client = hybrid_search.get_opensearch_client()
    if index == INDEX_STANDARD:
        body = {"size": FETCH_K, "query": {"match": {"text": query}}}
    else:
        body = {"size": FETCH_K, "query": {"match": {"search_tokens": " ".join(hybrid_search._tokenize(query))}}}
    return [hit["_source"]["chunk_key"] for hit in client.search(index=index, body=body)["hits"]["hits"]]


def rrf(rankings: List[List[str]], weights: List[float]) -> List[str]:
    """운영 hybrid_search.reciprocal_rank_fusion과 같은 식(1/(k+rank+1))에 검색기별 가중치를 곱한다.
    가중치가 모두 1이면 운영 코드와 같은 순서가 나온다."""
    scores: Dict[str, float] = defaultdict(float)
    for ranking, weight in zip(rankings, weights):
        for rank, key in enumerate(ranking):
            scores[key] += weight / (config.RRF_K + rank + 1)
    return sorted(scores, key=lambda k: scores[k], reverse=True)[:FETCH_K]


def run_query(state: dict, query: str) -> Dict[str, List[str]]:
    with contextlib.redirect_stdout(io.StringIO()):
        klue = search_dense(state["klue"], embedding.get_embedding(query).tolist(), "L2")
        ko = search_dense(state["ko"], state["ko_embed"](query), "IP")
        standard = search_sparse(INDEX_STANDARD, query)
        wordpiece = search_sparse(INDEX_WORDPIECE, query)
    return {
        "dense_klue": klue,
        "dense_ko": ko,
        "bm25_standard": standard,
        "bm25_wordpiece": wordpiece,
        "hybrid": rrf([klue, wordpiece], [1, 1]),
        "hybrid_bm25x2": rrf([klue, wordpiece], [1, 2]),
        "hybrid_ko": rrf([ko, wordpiece], [1, 1]),
        "hybrid_ko_bm25x2": rrf([ko, wordpiece], [1, 2]),
    }


def hit_at(ranking: List[str], relevant: List[str], k: int) -> float:
    return float(bool(set(ranking[:k]) & set(relevant)))


def summarize(rows: List[dict]) -> Dict[str, Dict[str, float]]:
    # 정답이 여러 청크일 수 있다(같은 문장을 실은 다른 매체). Hit@k는 "정답 중 하나라도 상위 k에 있는가".
    n = max(1, len(rows))
    out = {}
    for name in CONFIGS:
        out[name] = {
            "hit@1": sum(hit_at(r["rankings"][name], r["relevant"], 1) for r in rows) / n,
            "hit@10": sum(hit_at(r["rankings"][name], r["relevant"], 10) for r in rows) / n,
            "hit@20": sum(hit_at(r["rankings"][name], r["relevant"], 20) for r in rows) / n,
            "mrr@10": sum(metrics.reciprocal_rank(r["rankings"][name][:10], r["relevant"]) for r in rows) / n,
        }
    return out


def print_table(title: str, summary: Dict[str, Dict[str, float]], n: int) -> None:
    print(f"\n  {title} (질의 {n}개)")
    print(f"  {'설정':<18}{'Hit@1':>7}{'Hit@10':>8}{'Hit@20':>8}{'MRR@10':>8}")
    for name in CONFIGS:
        s = summary[name]
        print(f"  {name:<18}{s['hit@1']:>7.3f}{s['hit@10']:>8.3f}{s['hit@20']:>8.3f}{s['mrr@10']:>8.3f}")


def main() -> None:
    corpus = {a["id"]: a for a in load_jsonl(CORPUS)}
    queries = load_jsonl(QUERIES)
    paraphrases = {p["sentence_sha1"]: p["paraphrase"] for p in load_jsonl(PARAPHRASES)} if PARAPHRASES.exists() else {}
    chunks = build_chunks(list(corpus.values()))
    print(f"articles {len(corpus)}, chunks {len(chunks)}, query sentences {len(queries)}, paraphrases {len(paraphrases)}")

    start = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        ko_embed = KoEmbedder(KO_MODEL)
        milvus_store.ensure_milvus_connection()
        keys = [c["key"] for c in chunks]
        klue = index_dense(COLLECTION_KLUE, config.VECTOR_DIM, "L2",
                           [embedding.get_embedding(c["text"]).tolist() for c in chunks], keys)
        ko_vectors = [ko_embed(c["text"]) for c in chunks]
        ko = index_dense(COLLECTION_KO, len(ko_vectors[0]), "IP", ko_vectors, keys)
        index_sparse(chunks)
    print(f"indexed in {time.time() - start:.1f}s")
    state = {"klue": klue, "ko": ko, "ko_embed": ko_embed}

    rows, skipped, overlaps = [], 0, defaultdict(list)
    try:
        for q in queries:
            relevant = ds.relevant_chunk_keys(corpus, q["article_id"], q["sentence_sha1"])
            if not relevant:
                skipped += 1
                continue
            sentence = next(s for s in ds.split_sentences(corpus[q["article_id"]]["body"])
                            if ds.sha1(s) == q["sentence_sha1"])
            texts = {"verbatim": q["verbatim"], "keyword": q["keyword"]}
            if q["sentence_sha1"] in paraphrases:
                texts["paraphrase"] = paraphrases[q["sentence_sha1"]]
            for query_type, text in texts.items():
                overlap = ds.content_overlap(text, sentence)
                overlaps[query_type].append(overlap)
                rows.append({"id": q["id"], "type": query_type, "query": text, "overlap": round(overlap, 3),
                             "has_number": ds.query_has_number(q), "relevant": relevant,
                             "rankings": run_query(state, text)})
    finally:
        with contextlib.redirect_stdout(io.StringIO()):
            for name in (COLLECTION_KLUE, COLLECTION_KO):
                if utility.has_collection(name):
                    utility.drop_collection(name)
            hybrid_search.get_opensearch_client().indices.delete(
                index=f"{INDEX_STANDARD},{INDEX_WORDPIECE}", ignore_unavailable=True)

    groups = defaultdict(list)
    for row in rows:
        groups[row["type"]].append(row)
        if row["type"] == "keyword":
            groups["keyword_with_number" if row["has_number"] else "keyword_without_number"].append(row)
    groups["all"] = rows

    report = {
        "dataset": {"articles": len(corpus), "chunks": len(chunks), "query_sentences": len(queries) - skipped,
                    "skipped_sentences": skipped,
                    "multi_relevant_sentences": sum(1 for r in rows if r["type"] == "keyword" and len(r["relevant"]) > 1),
                    "fetch_k": FETCH_K, "rrf_k": config.RRF_K,
                    "embedding_models": {"dense_klue": config.EMBEDDING_MODEL_NAME, "dense_ko": KO_MODEL},
                    "mean_word_overlap_with_source": {t: round(sum(v) / len(v), 3) for t, v in overlaps.items()}},
        "summary": {name: summarize(group) for name, group in groups.items()},
        "counts": {name: len(group) for name, group in groups.items()},
        "per_query": rows,
    }
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    bar = "=" * 60
    print(f"\n{bar}\n  검색 설정 비교 (정답 = 질의를 만든 문장이 들어 있는 청크)\n{bar}")
    print("  원문 문장과 겹치는 단어 비율:", report["dataset"]["mean_word_overlap_with_source"])
    for name, title in (("verbatim", "verbatim: 문장 어절 그대로"), ("keyword", "keyword: 조사 제거 명사 위주"),
                        ("paraphrase", "paraphrase: 다른 말로 쓴 질문"),
                        ("keyword_with_number", "keyword 중 숫자 포함"), ("all", "전체")):
        if name in groups:
            print_table(title, report["summary"][name], len(groups[name]))
    print(f"\n  skipped sentences (article changed): {skipped}")
    print(f"  results: {RESULTS.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
