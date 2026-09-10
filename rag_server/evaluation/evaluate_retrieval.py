"""Run retriever evaluation against a versioned Golden Dataset.

Live mode uses the production Milvus retrieval function. Fixture mode makes the
same calculation reproducible in CI without GPU, Milvus, or API credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank, summarize


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            missing = {"id", "query", "relevant_document_ids"} - record.keys()
            if missing:
                raise ValueError(f"{path}:{number} is missing {', '.join(sorted(missing))}")
            if not isinstance(record["relevant_document_ids"], list):
                raise ValueError(f"{path}:{number} relevant_document_ids must be a list")
            records.append(record)
    if not records:
        raise ValueError(f"{path} has no evaluation records")
    return records


def load_fixture(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as source:
        fixture = json.load(source)
    if not isinstance(fixture, dict):
        raise ValueError("Fixture must map Golden Dataset IDs to result lists")
    return fixture


def retrieve_live(query: str, top_k: int) -> list[dict[str, Any]]:
    # Deferred imports prevent the evaluator's metric-only mode from downloading
    # an embedding model or connecting to Milvus.
    import config
    import utils

    embedding = utils.get_embedding(query)
    if embedding is None:
        raise RuntimeError("Embedding generation failed")
    return utils.search_milvus(embedding, config.COLLECTION_NAMES, top_k)


def evaluate(dataset: list[dict[str, Any]], top_k: int, fixture: dict[str, list[dict[str, Any]]] | None) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for case in dataset:
        started = time.perf_counter()
        results = fixture.get(case["id"], []) if fixture is not None else retrieve_live(case["query"], top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        relevant = case["relevant_document_ids"]
        rows.append({
            "id": case["id"],
            "category": case.get("category", "uncategorized"),
            "answerable": case.get("answerable", True),
            "relevant_document_ids": relevant,
            "retrieved_document_ids": [f"{item['collection']}:{item['id']}" for item in results[:top_k]],
            "recall_at_k": recall_at_k(results, relevant, top_k),
            "mrr": reciprocal_rank(results, relevant),
            "ndcg_at_k": ndcg_at_k(results, relevant, top_k),
            "latency_ms": round(latency_ms, 3),
        })
    return rows, summarize(rows, top_k)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate MyAnalyst retrieval quality")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("evaluation-report.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--fixture", type=Path, help="Optional deterministic retrieval fixture for CI")
    parser.add_argument("--min-recall-at-k", type=float, help="Fail when mean Recall@K falls below this threshold")
    parser.add_argument("--min-mrr", type=float, help="Fail when mean MRR falls below this threshold")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    dataset = read_jsonl(args.dataset)
    fixture = load_fixture(args.fixture) if args.fixture else None
    rows, summary = evaluate(dataset, args.top_k, fixture)
    report = {"summary": summary, "cases": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.min_recall_at_k is not None and summary["recall_at_k"] < args.min_recall_at_k:
        print("Recall@K is below the configured quality gate", file=sys.stderr)
        return 2
    if args.min_mrr is not None and summary["mrr"] < args.min_mrr:
        print("MRR is below the configured quality gate", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
