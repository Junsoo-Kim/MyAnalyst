"""공개 한국어 검색 벤치마크로 같은 검색 설정을 비교한다. 자체 데이터 결과가 데이터 편향 때문이 아닌지 확인하는
교차 검증용이다(OpenAI 호출 없음).

  docker compose run --rm --no-deps -v ./services/knowledge:/src -v <hf-cache-dir>:/hfcache -e PYTHONPATH=/src -w /src \
      knowledge python -m evals.public_benchmark_eval [ko_strategyqa|autorag]

autorag는 parquet 파일이라 pyarrow가 필요하다(서비스 이미지에는 없으므로 실행 전에
`pip install --target /tmp/pydeps pyarrow`로 설치하고 PYTHONPATH에 /tmp/pydeps를 더한다).

ko_strategyqa: Hugging Face `taeminlee/Ko-StrategyQA`(StrategyQA를 한국어로 옮긴 것, MTEB 한국어 검색 과제 중 하나).
문단 9,251개, dev 질의 592개, 질의당 정답 문단 평균 1.9개(사람이 근거 문단으로 표시한 것). 실행할 때 내려받으며
저장소에는 넣지 않는다. 문서는 MTEB와 같이 "제목 + 본문"으로 색인한다.
질의가 "줄리어스 시저는 몇 명의 자녀를 두었나요?" 같은 자연어 질문이라, 자체 데이터의 paraphrase와 성격이 가깝다.

autorag: Hugging Face `mteb/AutoRAGRetrieval`(Allganize RAG 리더보드 데이터를 MTEB 검색 과제로 옮긴 것). 금융·공공·
법률·커머스 PDF 문서 페이지 720개, 질의 114개(금융 22개), 질의당 정답 페이지 1개(사람 라벨).
"""
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

from huggingface_hub import hf_hub_download

from evals import stats
from evals.retrieval_engine import CONFIGS, FETCH_K, HF_CACHE, KO_MODEL, Engine

import config

HERE = Path(__file__).resolve().parent
DATASETS = {
    "ko_strategyqa": {"repo": "taeminlee/Ko-StrategyQA", "split": "dev"},
    "autorag": {"repo": "mteb/AutoRAGRetrieval", "split": "test"},
}
METRICS = ["hit@10", "hit@20", "recall@20", "ndcg@10", "mrr@10"]

COMPARISONS = [
    ("도입 전후: Dense 단독(원래) → 하이브리드(현재)", "dense_klue", "hybrid"),
    ("토큰화 수정: BM25 standard → WordPiece", "bm25_standard", "bm25_wordpiece"),
    ("상호 보완: BM25 단독 → 하이브리드", "bm25_wordpiece", "hybrid"),
    ("BM25 가중: 하이브리드 1:1 → 1:2", "hybrid", "hybrid_bm25x2"),
    ("임베딩 모델: 하이브리드(klue) → 하이브리드(ko-sroberta)", "hybrid", "hybrid_ko"),
]


def download(repo: str, name: str) -> Path:
    return Path(hf_hub_download(repo, name, repo_type="dataset", cache_dir=HF_CACHE))


def load_ko_strategyqa(repo: str):
    def lines(name: str) -> List[str]:
        return [line for line in download(repo, name).read_text(encoding="utf-8").splitlines() if line]

    corpus = [json.loads(line) for line in lines("corpus.jsonl")]
    queries = {q["_id"]: q["text"] for q in map(json.loads, lines("queries.jsonl"))}
    qrels = [line.split("\t") for line in lines("qrels/dev.tsv")[1:]]
    return corpus, queries, qrels


def load_autorag(repo: str):
    import pandas as pd

    def table(name: str) -> List[dict]:
        return pd.read_parquet(download(repo, f"{name}/test-00000-of-00001.parquet")).to_dict("records")

    queries = {q["_id"]: q["text"] for q in table("queries")}
    qrels = [(r["query-id"], r["corpus-id"], r["score"]) for r in table("qrels")]
    return table("corpus"), queries, qrels


LOADERS = {"ko_strategyqa": load_ko_strategyqa, "autorag": load_autorag}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "ko_strategyqa"
    dataset = DATASETS[name]
    repo = dataset["repo"]
    results_path = HERE / "results" / f"public_benchmark_{name}.json"
    corpus, queries, raw_qrels = LOADERS[name](repo)
    qrels: Dict[str, List[str]] = {}
    for qid, doc_id, score in raw_qrels:
        if float(score) > 0:
            qrels.setdefault(qid, []).append(doc_id)
    query_ids = [qid for qid in qrels if qid in queries]
    docs = [{"key": d["_id"], "text": f"{d.get('title', '')} {d['text']}".strip()} for d in corpus]
    print(f"{repo} {dataset['split']}: docs {len(docs)}, queries {len(query_ids)}, "
          f"avg relevant {sum(len(qrels[q]) for q in query_ids) / len(query_ids):.2f}")

    engine = Engine("eval_public")
    start = time.time()
    try:
        engine.build(docs)
        rankings = engine.search_many([queries[q] for q in query_ids])
    finally:
        engine.cleanup()
    print(f"searched {len(query_ids)} queries; total {time.time() - start:.0f}s")

    per = {name: [stats.per_query(r[name], qrels[q]) for q, r in zip(query_ids, rankings)] for name in CONFIGS}
    summary = {name: {m: stats.mean_ci([x[m] for x in per[name]], query_ids) for m in METRICS} for name in CONFIGS}
    comparisons = []
    for title, base, other in COMPARISONS:
        for m in METRICS:
            result = stats.compare([x[m] for x in per[base]], [x[m] for x in per[other]], query_ids,
                                   binary=m.startswith("hit"))
            comparisons.append({"title": title, "base": base, "other": other, "metric": m, **result})

    report = {
        "dataset": {"name": repo, "split": dataset["split"], "docs": len(docs), "queries": len(query_ids), "fetch_k": FETCH_K,
                    "rrf_k": config.RRF_K,
                    "embedding_models": {"dense_klue": config.EMBEDDING_MODEL_NAME, "dense_ko": KO_MODEL}},
        "summary": summary,
        "comparisons": comparisons,
        "per_query": [{"id": q, "relevant": qrels[q], "rankings": r} for q, r in zip(query_ids, rankings)],
    }
    results_path.parent.mkdir(exist_ok=True)
    results_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n  {'설정':<18}" + "".join(f"{m:>22}" for m in METRICS))
    for name in CONFIGS:
        print(f"  {name:<18}" + "".join(f"{s['mean']:>8.3f} [{s['lo']:.3f}-{s['hi']:.3f}]"
                                       for s in (summary[name][m] for m in METRICS)))
    print("\n  짝지은 비교 (b - a, 95% CI, p)")
    for c in comparisons:
        extra = f" (a만 {c['only_a']}, b만 {c['only_b']})" if "only_a" in c else ""
        print(f"  {c['title']} | {c['metric']:<9} {c['a']:.3f} -> {c['b']:.3f} Δ{c['delta']:+.3f} "
              f"[{c['lo']:+.3f}, {c['hi']:+.3f}] p={stats.fmt_p(c['p'])}{extra}")
    print(f"\n  results: {results_path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
