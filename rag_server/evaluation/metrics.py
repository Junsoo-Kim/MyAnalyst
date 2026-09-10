"""Deterministic retrieval metrics used by the Golden Dataset evaluator."""

from __future__ import annotations

import math
from statistics import median
from typing import Iterable, Sequence


def document_key(item: object) -> str:
    """Return the stable ID used in evaluation data: ``collection:id``.

    The RAG search result itself may contain a numeric Milvus ID; pairing it
    with the collection prevents collisions across the two current collections.
    """
    if isinstance(item, str):
        return item
    if not isinstance(item, dict) or "collection" not in item or "id" not in item:
        raise ValueError("A retrieval result must contain collection and id")
    return f"{item['collection']}:{item['id']}"


def unique_ranking(results: Iterable[object]) -> list[str]:
    ranking: list[str] = []
    seen: set[str] = set()
    for item in results:
        key = document_key(item)
        if key not in seen:
            ranking.append(key)
            seen.add(key)
    return ranking


def recall_at_k(results: Sequence[object], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    hits = len(set(unique_ranking(results)[:k]) & relevant_set)
    return hits / len(relevant_set)


def reciprocal_rank(results: Sequence[object], relevant: Iterable[str]) -> float:
    relevant_set = set(relevant)
    for position, key in enumerate(unique_ranking(results), start=1):
        if key in relevant_set:
            return 1.0 / position
    return 0.0


def ndcg_at_k(results: Sequence[object], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    ranking = unique_ranking(results)[:k]
    dcg = sum(1.0 / math.log2(position + 1) for position, key in enumerate(ranking, start=1)
              if key in relevant_set)
    ideal_hits = min(k, len(relevant_set))
    ideal_dcg = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    ordered = sorted(values)
    index = (len(ordered) - 1) * p / 100
    lower, upper = math.floor(index), math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def summarize(rows: Sequence[dict], k: int) -> dict:
    labeled = [row for row in rows if row["relevant_document_ids"]]
    latencies = [row["latency_ms"] for row in rows]
    return {
        "query_count": len(rows),
        "labeled_query_count": len(labeled),
        "k": k,
        "recall_at_k": sum(row["recall_at_k"] for row in labeled) / len(labeled) if labeled else 0.0,
        "mrr": sum(row["mrr"] for row in labeled) / len(labeled) if labeled else 0.0,
        "ndcg_at_k": sum(row["ndcg_at_k"] for row in labeled) / len(labeled) if labeled else 0.0,
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies, default=0.0),
        },
    }
