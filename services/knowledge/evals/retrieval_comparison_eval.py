"""자체 데이터(셀트리온 뉴스)로 검색 설정을 비교한다(OpenAI 호출 없음). 설정 목록은 retrieval_engine 참고.

  docker compose up -d --wait etcd minio milvus opensearch
  docker compose run --rm --no-deps -v ./services/knowledge:/src -v <hf-cache-dir>:/hfcache -e PYTHONPATH=/src -w /src \
      knowledge python -m evals.retrieval_comparison_eval

데이터: evals/data/corpus.local.jsonl(build_retrieval_dataset.py로 생성), queries.jsonl, paraphrases.jsonl.

질의 유형(같은 정답 문장에서 만든 세 가지):
  verbatim    문장 어절 그대로 앞 5개
  keyword     조사를 떼고 명사 위주 5개 (생성 파이프라인의 LLM 키워드와 같은 모양)
  paraphrase  원문 단어를 피해 다른 말로 쓴 질문 (paraphrases.jsonl)
정답: 그 문장이 들어 있는 청크, 그리고 다른 매체가 거의 같게 쓴 문장이 들어 있는 청크.
"""
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from evals import retrieval_dataset as ds
from evals import stats
from evals.retrieval_engine import CONFIGS, FETCH_K, KO_MODEL, Engine

import config

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "data" / "corpus.local.jsonl"
QUERIES = HERE / "data" / "queries.jsonl"
PARAPHRASES = HERE / "data" / "paraphrases.jsonl"
RESULTS = HERE / "results" / "retrieval_comparison.json"
METRICS = ["hit@1", "hit@10", "hit@20", "mrr@10"]

# (이름, 기준 설정, 비교 설정, 질의 묶음, 지표)
COMPARISONS = [
    ("도입 전후: Dense 단독(원래) → 하이브리드(현재)", "dense_klue", "hybrid",
     ["keyword", "paraphrase", "verbatim", "all"], ["hit@20", "hit@10", "mrr@10"]),
    ("토큰화 수정: BM25 standard → WordPiece", "bm25_standard", "bm25_wordpiece",
     ["keyword", "keyword_with_number", "paraphrase"], ["hit@1", "mrr@10", "hit@20"]),
    ("상호 보완: BM25 단독 → 하이브리드", "bm25_wordpiece", "hybrid",
     ["paraphrase", "keyword", "all"], ["hit@20", "mrr@10"]),
    ("BM25 가중: 하이브리드 1:1 → 1:2", "hybrid", "hybrid_bm25x2",
     ["paraphrase", "keyword", "all"], ["hit@20", "mrr@10"]),
    ("임베딩 모델: 하이브리드(klue) → 하이브리드(ko-sroberta)", "hybrid", "hybrid_ko",
     ["paraphrase", "keyword", "all"], ["hit@20", "mrr@10"]),
]


def load_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    corpus = {a["id"]: a for a in load_jsonl(CORPUS)}
    queries = load_jsonl(QUERIES)
    paraphrases = {p["sentence_sha1"]: p["paraphrase"] for p in load_jsonl(PARAPHRASES)}
    docs = [{"key": f"{a['id']}:{i}", "text": t}
            for a in corpus.values() for i, t in enumerate(ds.chunk_article(a["body"]))]
    print(f"articles {len(corpus)}, chunks {len(docs)}, query sentences {len(queries)}, paraphrases {len(paraphrases)}")

    # 정답 청크와 질의 문자열 준비(검색 전에 확정한다)
    pending, skipped = [], 0
    for q in queries:
        relevant = ds.relevant_chunk_keys(corpus, q["article_id"], q["sentence_sha1"])
        if not relevant:
            skipped += 1
            continue
        sentence = next(s for s in ds.split_sentences(corpus[q["article_id"]]["body"]) if ds.sha1(s) == q["sentence_sha1"])
        texts = {"verbatim": q["verbatim"], "keyword": q["keyword"]}
        if q["sentence_sha1"] in paraphrases:
            texts["paraphrase"] = paraphrases[q["sentence_sha1"]]
        for query_type, text in texts.items():
            pending.append({"id": q["id"], "type": query_type, "query": text,
                            "overlap": round(ds.content_overlap(text, sentence), 3),
                            "has_number": ds.query_has_number(q), "relevant": relevant})

    engine = Engine("eval_retrieval")
    start = time.time()
    try:
        engine.build(docs)
        rankings = engine.search_many([row["query"] for row in pending])
    finally:
        engine.cleanup()
    print(f"searched {len(pending)} queries; total {time.time() - start:.0f}s")

    rows = []
    for row, ranking in zip(pending, rankings):
        row["rankings"] = ranking
        row["metrics"] = {name: stats.per_query(ranking[name], row["relevant"]) for name in CONFIGS}
        rows.append(row)

    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[row["type"]].append(row)
        groups["all"].append(row)
        if row["type"] == "keyword" and row["has_number"]:
            groups["keyword_with_number"].append(row)

    summary = {}
    for group, members in groups.items():
        ids = [r["id"] for r in members]
        summary[group] = {name: {m: stats.mean_ci([r["metrics"][name][m] for r in members], ids) for m in METRICS}
                          for name in CONFIGS}

    comparisons = []
    for title, base, other, group_names, metrics in COMPARISONS:
        for group in group_names:
            members = groups[group]
            ids = [r["id"] for r in members]
            for m in metrics:
                result = stats.compare([r["metrics"][base][m] for r in members],
                                       [r["metrics"][other][m] for r in members], ids, binary=m.startswith("hit"))
                comparisons.append({"title": title, "base": base, "other": other, "group": group, "n": len(members),
                                    "metric": m, **result})

    overlaps = defaultdict(list)
    for row in rows:
        overlaps[row["type"]].append(row["overlap"])
    report = {
        "dataset": {"articles": len(corpus), "chunks": len(docs), "query_sentences": len(queries) - skipped,
                    "skipped_sentences": skipped,
                    "multi_relevant_sentences": sum(1 for r in groups["keyword"] if len(r["relevant"]) > 1),
                    "fetch_k": FETCH_K, "rrf_k": config.RRF_K,
                    "embedding_models": {"dense_klue": config.EMBEDDING_MODEL_NAME, "dense_ko": KO_MODEL},
                    "mean_word_overlap_with_source": {t: round(sum(v) / len(v), 3) for t, v in overlaps.items()}},
        "counts": {g: len(m) for g, m in groups.items()},
        "summary": summary,
        "comparisons": comparisons,
        "per_query": [{k: v for k, v in r.items() if k != "metrics"} for r in rows],
    }
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n  원문 문장과 겹치는 단어 비율:", report["dataset"]["mean_word_overlap_with_source"])
    for group in ("verbatim", "keyword", "paraphrase", "keyword_with_number", "all"):
        print(f"\n  [{group}] 질의 {len(groups[group])}개  (평균 [95% CI])")
        print(f"  {'설정':<18}" + "".join(f"{m:>22}" for m in ("hit@20", "hit@10", "mrr@10")))
        for name in CONFIGS:
            cells = "".join(f"{s['mean']:>8.3f} [{s['lo']:.3f}-{s['hi']:.3f}]"
                            for s in (summary[group][name][m] for m in ("hit@20", "hit@10", "mrr@10")))
            print(f"  {name:<18}{cells}")
    print("\n  짝지은 비교 (b - a, 95% CI, p)")
    for c in comparisons:
        extra = f" (a만 {c['only_a']}, b만 {c['only_b']})" if "only_a" in c else ""
        print(f"  {c['title']} | {c['group']:<20} {c['metric']:<7} {c['a']:.3f} -> {c['b']:.3f} "
              f"Δ{c['delta']:+.3f} [{c['lo']:+.3f}, {c['hi']:+.3f}] p={stats.fmt_p(c['p'])}{extra}")
    print(f"\n  results: {RESULTS.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
