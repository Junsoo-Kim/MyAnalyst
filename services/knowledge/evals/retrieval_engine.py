"""검색 비교 평가 공용 엔진: 문서를 평가 전용 Milvus 컬렉션·OpenSearch 인덱스에 넣고, 설정별로 검색한다.
retrieval_comparison_eval(자체 데이터)과 public_benchmark_eval(공개 벤치마크)이 같은 코드를 쓴다.
운영 인덱스는 건드리지 않는다(이름에 prefix를 붙인 평가 전용 컬렉션·인덱스를 만들고 cleanup()으로 지운다).

설정(검색기마다 상위 FETCH_K개를 가져온다. 하이브리드는 RRF로 합친 뒤 상위 FETCH_K개):
  dense_klue         klue/bert-base 평균 풀링 + L2 (현재 운영 임베딩, embedding.py와 같은 풀링)
  dense_ko           jhgan/ko-sroberta-multitask(한국어 문장 임베딩) 평균 풀링 + 코사인
  bm25_standard      OpenSearch 기본 분석기 (토큰화 수정 전)
  bm25_wordpiece     KLUE-BERT WordPiece 사전 토큰화 (현재 운영, hybrid_search._tokenize)
  hybrid             dense_klue + bm25_wordpiece, RRF 1:1 (현재 운영)
  hybrid_bm25x2      dense_klue + bm25_wordpiece, RRF 1:2 (BM25 가중)
  hybrid_ko          dense_ko + bm25_wordpiece, RRF 1:1
  hybrid_ko_bm25x2   dense_ko + bm25_wordpiece, RRF 1:2
"""
import contextlib
import io
import os
import time
import warnings
from collections import defaultdict
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

KO_MODEL = os.getenv("EVAL_KO_EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
HF_CACHE = os.getenv("EVAL_HF_CACHE", "/hfcache")
FETCH_K = config.SEARCH_TOP_K  # 20: 생성 파이프라인이 검색 결과를 받아 LLM 채점에 넘기는 후보 수
BATCH = 32
CONFIGS = ["dense_klue", "dense_ko", "bm25_standard", "bm25_wordpiece",
           "hybrid", "hybrid_bm25x2", "hybrid_ko", "hybrid_ko_bm25x2"]


def _mean_pool(last_hidden: "torch.Tensor", mask: "torch.Tensor") -> "torch.Tensor":
    mask = mask.unsqueeze(-1).float()
    return (last_hidden * mask).sum(1) / torch.clamp(mask.sum(1), min=1e-9)


def embed_klue(texts: List[str]) -> List[List[float]]:
    """embedding.get_embedding과 같은 계산(같은 모델·토크나이저·max_length·평균 풀링)을 배치로 한다.
    패딩 토큰은 attention mask로 빠지므로 한 건씩 계산한 결과와 같다."""
    embedding.initialize_models()
    out = []
    for i in range(0, len(texts), BATCH):
        encoded = embedding.tokenizer(texts[i:i + BATCH], padding=True, truncation=True, max_length=512,
                                      return_tensors="pt").to(embedding.device)
        with torch.no_grad():
            hidden = embedding.embedding_model(**encoded)[0]
        out.extend(_mean_pool(hidden, encoded["attention_mask"]).cpu().tolist())
    return out


class KoEmbedder:
    """sentence-transformers 없이 같은 방식(평균 풀링 + L2 정규화)으로 문장 임베딩을 만든다."""

    def __init__(self, name: str = KO_MODEL):
        self.tokenizer = AutoTokenizer.from_pretrained(name, cache_dir=HF_CACHE)
        self.model = AutoModel.from_pretrained(name, cache_dir=HF_CACHE).eval()

    def __call__(self, texts: List[str]) -> List[List[float]]:
        out = []
        for i in range(0, len(texts), BATCH):
            encoded = self.tokenizer(texts[i:i + BATCH], padding=True, truncation=True, max_length=256,
                                     return_tensors="pt")
            with torch.no_grad():
                hidden = self.model(**encoded).last_hidden_state
            out.extend(torch.nn.functional.normalize(_mean_pool(hidden, encoded["attention_mask"]), dim=1).tolist())
        return out


def rrf(rankings: List[List[str]], weights: List[float]) -> List[str]:
    """운영 hybrid_search.reciprocal_rank_fusion과 같은 식(1/(k+rank+1))에 검색기별 가중치를 곱한다.
    가중치가 모두 1이면 운영 코드와 같은 순서가 나온다."""
    scores: Dict[str, float] = defaultdict(float)
    for ranking, weight in zip(rankings, weights):
        for rank, key in enumerate(ranking):
            scores[key] += weight / (config.RRF_K + rank + 1)
    return sorted(scores, key=lambda k: scores[k], reverse=True)[:FETCH_K]


class Engine:
    def __init__(self, prefix: str):
        self.collection_klue = f"{prefix}_klue"
        self.collection_ko = f"{prefix}_ko"
        self.index_standard = f"{prefix}-standard".replace("_", "-")
        self.index_wordpiece = f"{prefix}-wordpiece".replace("_", "-")
        self.ko = None
        self.collections: Dict[str, Collection] = {}

    # --- 색인 ---------------------------------------------------------------------------------

    def build(self, docs: List[dict], log=print) -> None:
        """docs: [{"key": 문서 키, "text": 본문}]"""
        start = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            milvus_store.ensure_milvus_connection()
            self.ko = KoEmbedder()
        keys, texts = [d["key"] for d in docs], [d["text"] for d in docs]
        klue_vectors = embed_klue(texts)
        log(f"  dense_klue embedded {len(texts)} docs ({time.time() - start:.0f}s)")
        ko_vectors = self.ko(texts)
        log(f"  dense_ko embedded {len(texts)} docs ({time.time() - start:.0f}s)")
        with contextlib.redirect_stdout(io.StringIO()):
            self.collections["klue"] = self._index_dense(self.collection_klue, "L2", klue_vectors, keys)
            self.collections["ko"] = self._index_dense(self.collection_ko, "IP", ko_vectors, keys)
            self._index_sparse(keys, texts)
        log(f"  indexed in {time.time() - start:.0f}s")

    def _index_dense(self, name: str, metric: str, vectors: List[List[float]], keys: List[str]) -> Collection:
        if utility.has_collection(name):
            utility.drop_collection(name)
        collection = Collection(name, schema=CollectionSchema([
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=len(vectors[0])),
            FieldSchema(name="doc_key", dtype=DataType.VARCHAR, max_length=256),
        ]))
        collection.create_index("embedding", {"index_type": "FLAT", "metric_type": metric, "params": {}})
        for i in range(0, len(keys), 1000):
            collection.insert([list(range(i, min(i + 1000, len(keys)))), vectors[i:i + 1000], keys[i:i + 1000]])
        collection.flush()
        collection.load()
        return collection

    def _index_sparse(self, keys: List[str], texts: List[str]) -> None:
        client = hybrid_search.get_opensearch_client()
        for name, mapping in (
            (self.index_standard, {"text": {"type": "text", "analyzer": "standard"}}),
            (self.index_wordpiece, {"search_tokens": {"type": "text", "analyzer": "whitespace"}}),
        ):
            if client.indices.exists(index=name):
                client.indices.delete(index=name)
            client.indices.create(index=name, body={
                "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {"properties": {"doc_key": {"type": "keyword"}, **mapping}},
            })
        helpers.bulk(client, ({"_index": self.index_standard, "_id": k, "_source": {"doc_key": k, "text": t}}
                              for k, t in zip(keys, texts)), chunk_size=500, request_timeout=120)
        helpers.bulk(client, ({"_index": self.index_wordpiece, "_id": k,
                               "_source": {"doc_key": k, "search_tokens": " ".join(hybrid_search._tokenize(t))}}
                              for k, t in zip(keys, texts)), chunk_size=500, request_timeout=120)
        client.indices.refresh(index=f"{self.index_standard},{self.index_wordpiece}")

    # --- 검색 ---------------------------------------------------------------------------------

    def _dense(self, which: str, vector: List[float], metric: str) -> List[str]:
        hits = self.collections[which].search([vector], "embedding", {"metric_type": metric, "params": {}},
                                              limit=FETCH_K, output_fields=["doc_key"])[0]
        return [hit.entity.get("doc_key") for hit in hits]

    def _sparse(self, index: str, query: str) -> List[str]:
        client = hybrid_search.get_opensearch_client()
        if index == self.index_standard:
            body = {"size": FETCH_K, "query": {"match": {"text": query}}}
        else:
            body = {"size": FETCH_K, "query": {"match": {"search_tokens": " ".join(hybrid_search._tokenize(query))}}}
        return [hit["_source"]["doc_key"] for hit in client.search(index=index, body=body)["hits"]["hits"]]

    def search_many(self, queries: List[str]) -> List[Dict[str, List[str]]]:
        klue_vectors = embed_klue(queries)
        ko_vectors = self.ko(queries)
        results = []
        with contextlib.redirect_stdout(io.StringIO()):
            for query, klue_vector, ko_vector in zip(queries, klue_vectors, ko_vectors):
                klue = self._dense("klue", klue_vector, "L2")
                ko = self._dense("ko", ko_vector, "IP")
                standard = self._sparse(self.index_standard, query)
                wordpiece = self._sparse(self.index_wordpiece, query)
                results.append({
                    "dense_klue": klue,
                    "dense_ko": ko,
                    "bm25_standard": standard,
                    "bm25_wordpiece": wordpiece,
                    "hybrid": rrf([klue, wordpiece], [1, 1]),
                    "hybrid_bm25x2": rrf([klue, wordpiece], [1, 2]),
                    "hybrid_ko": rrf([ko, wordpiece], [1, 1]),
                    "hybrid_ko_bm25x2": rrf([ko, wordpiece], [1, 2]),
                })
        return results

    def cleanup(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            for name in (self.collection_klue, self.collection_ko):
                if utility.has_collection(name):
                    utility.drop_collection(name)
            hybrid_search.get_opensearch_client().indices.delete(
                index=f"{self.index_standard},{self.index_wordpiece}", ignore_unavailable=True)
