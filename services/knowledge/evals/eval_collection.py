"""평가용 임시 Milvus 컬렉션 준비/정리.

검색 저장소는 knowledge가 소유하므로, 생성 워커의 환각 평가(corrective_rag_hallucination_eval)는
이 스크립트로 먼저 컬렉션을 만든 뒤 knowledge-service의 /search에 collections를 지정해 사용한다.

    python -m evals.eval_collection setup
    python -m evals.eval_collection cleanup
"""
import os
import sys

import pandas as pd

from evals.hybrid_search_recall_eval import CSV_PATH, EVAL_COLLECTION, build_corpus, cleanup, quiet, setup_eval_collection


def main(argv) -> int:
    if len(argv) != 2 or argv[1] not in ("setup", "cleanup"):
        print(__doc__)
        return 2
    if argv[1] == "cleanup":
        cleanup()
        return 0
    if not os.path.exists(CSV_PATH):
        print(f"오류: {CSV_PATH} 를 찾을 수 없습니다. docker-compose.yml의 볼륨 마운트를 확인하세요.")
        return 1
    records = build_corpus(pd.read_csv(CSV_PATH))
    with quiet():
        setup_eval_collection(records)
    print(f"Indexed {len(records)} chunks into temporary collection '{EVAL_COLLECTION}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
