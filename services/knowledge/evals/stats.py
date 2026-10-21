"""검색 평가용 지표와 통계(표준 라이브러리만 사용).

- 질의마다 hit@k, MRR@10, nDCG@10, recall@k를 계산한다(정답이 여러 개일 수 있다).
- 신뢰구간: 부트스트랩 95% 백분위 구간(2,000회). 같은 정답 문장에서 만든 질의 여러 개는 서로 독립이 아니므로
  묶음(cluster) 단위로 다시 뽑는다.
- 두 설정 비교(같은 질의에 둘 다 돌린 짝지은 비교):
  - 차이의 95% 부트스트랩 구간
  - hit 지표: McNemar 정확 검정(결과가 갈린 질의만 센다, 양측)
  - 연속 지표(MRR, nDCG): 부호 뒤집기 순열 검정(10,000회, 양측)
"""
import math
import random
from typing import Dict, List, Sequence

SEED = 20261021
BOOTSTRAP = 2000
PERMUTATIONS = 10000


def per_query(ranking: Sequence[str], relevant: Sequence[str]) -> Dict[str, float]:
    rel = set(relevant)
    first = next((i + 1 for i, key in enumerate(ranking) if key in rel), None)
    dcg = sum(1 / math.log2(i + 2) for i, key in enumerate(ranking[:10]) if key in rel)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(10, len(rel))))
    return {
        "hit@1": float(first == 1),
        "hit@10": float(first is not None and first <= 10),
        "hit@20": float(first is not None and first <= 20),
        "mrr@10": 1 / first if first is not None and first <= 10 else 0.0,
        "ndcg@10": dcg / ideal if ideal else 0.0,
        "recall@20": len(rel & set(ranking[:20])) / len(rel) if rel else 0.0,
    }


def _clusters(cluster_ids: Sequence[str]) -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = {}
    for i, c in enumerate(cluster_ids):
        groups.setdefault(c, []).append(i)
    return groups


def _resample(groups: Dict[str, List[int]], rng: random.Random) -> List[int]:
    keys = list(groups)
    idx: List[int] = []
    for _ in keys:
        idx.extend(groups[rng.choice(keys)])
    return idx


def _percentile(values: List[float], p: float) -> float:
    values = sorted(values)
    pos = (len(values) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def mean_ci(values: Sequence[float], cluster_ids: Sequence[str]) -> Dict[str, float]:
    rng = random.Random(SEED)
    groups = _clusters(cluster_ids)
    means = []
    for _ in range(BOOTSTRAP):
        idx = _resample(groups, rng)
        means.append(sum(values[i] for i in idx) / len(idx))
    return {"mean": sum(values) / len(values), "lo": _percentile(means, 0.025), "hi": _percentile(means, 0.975)}


def _mcnemar_exact(a: Sequence[float], b: Sequence[float]) -> Dict[str, float]:
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    n = only_a + only_b
    if n == 0:
        return {"only_a": 0, "only_b": 0, "p": 1.0}
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"only_a": only_a, "only_b": only_b, "p": min(1.0, 2 * tail)}


def _sign_flip(a: Sequence[float], b: Sequence[float]) -> float:
    rng = random.Random(SEED)
    diffs = [y - x for x, y in zip(a, b)]
    observed = abs(sum(diffs))
    if observed == 0:
        return 1.0
    extreme = 0
    for _ in range(PERMUTATIONS):
        if abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed - 1e-12:
            extreme += 1
    return (extreme + 1) / (PERMUTATIONS + 1)


def compare(a: Sequence[float], b: Sequence[float], cluster_ids: Sequence[str], binary: bool) -> Dict[str, float]:
    """b - a. binary면 McNemar, 아니면 부호 뒤집기 순열 검정."""
    rng = random.Random(SEED)
    groups = _clusters(cluster_ids)
    deltas = []
    for _ in range(BOOTSTRAP):
        idx = _resample(groups, rng)
        deltas.append(sum(b[i] - a[i] for i in idx) / len(idx))
    out = {"a": sum(a) / len(a), "b": sum(b) / len(b), "delta": (sum(b) - sum(a)) / len(a),
           "lo": _percentile(deltas, 0.025), "hi": _percentile(deltas, 0.975)}
    if binary:
        out.update(_mcnemar_exact(a, b))
    else:
        out["p"] = _sign_flip(a, b)
    return out


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"
