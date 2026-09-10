import contextlib
import io
import json
import os
import sys
import warnings
from typing import Dict, List

warnings.filterwarnings("ignore")

with contextlib.redirect_stdout(io.StringIO()):
    import pandas as pd
    from pymilvus import utility

    import config
    import hybrid_search
    import rag_report_pipeline
    import utils
    from evals.hybrid_search_recall_eval import CSV_PATH, EVAL_COLLECTION, build_corpus, setup_eval_collection

JUDGE_LLM_MODEL = os.getenv("JUDGE_LLM_MODEL", "gpt-4o")
SECTION_IDS = ["2", "3", "4", "5", "6"]
TOTAL_RUNS = 27

def build_run_plan() -> List[str]:
    base, extra = divmod(TOTAL_RUNS, len(SECTION_IDS))
    plan = []
    for i, sec_id in enumerate(SECTION_IDS):
        count = base + (1 if i < extra else 0)
        plan.extend([sec_id] * count)
    return plan

@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield

def confirm_cost() -> bool:
    print("=" * 62)
    print("  이 평가는 OpenAI API를 실제로 호출합니다 (비용 발생).")
    print(f"  생성 {TOTAL_RUNS}회 x 2가지 방식 = {TOTAL_RUNS * 2}회 생성 + 독립 채점(judge model={JUDGE_LLM_MODEL})")
    print("  진행하려면 y, 취소하려면 다른 키를 입력하세요.")
    print("=" * 62)
    try:
        answer = input("계속할까요? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer == "y"

def judge_grounding(context: str, section_content: str) -> Dict:
    prompt = f"""당신은 기업 분석 보고서를 검수하는 외부 감사역입니다.
아래 [생성된 보고서 섹션]의 문장 중, [제공된 근거 자료]만으로는 뒷받침되지 않는 사실·수치·주장이
담긴 문장이 있는지 엄격하게 찾아내세요. 목차 제목이나 일반적인 연결 문장은 판단 대상에서 제외하고,
실질적인 사실 주장(수치, 고유명사, 사건)만 판단하세요.

[제공된 근거 자료]
{context[:8000] if context else "(근거 자료 없음)"}

[생성된 보고서 섹션]
{section_content}

다음 JSON 형식으로만 답하세요:
{{"grounded": true 또는 false, "unsupported_claims": ["문제 문장1", "문제 문장2", ...]}}
"""
    try:
        client = utils.get_openai_client()
        response = client.chat.completions.create(
            model=JUDGE_LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a strict, independent factual auditor. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "grounded": bool(result.get("grounded", True)),
            "unsupported_claims": result.get("unsupported_claims", []),
        }
    except Exception as e:
        print(f"  [judge 실패] {e}")
        return {"grounded": None, "unsupported_claims": [], "error": str(e)}

def generate_sections(method_name: str, generator_fn, report_params: Dict) -> List[Dict]:
    captured = {"context": None}
    original_format_context = utils.format_context

    def capturing_format_context(chunks):
        ctx = original_format_context(chunks)
        captured["context"] = ctx
        return ctx

    utils.format_context = capturing_format_context

    run_plan = build_run_plan()
    run_counts: Dict[str, int] = {}

    results = []
    try:
        for i, sec_id in enumerate(run_plan):
            title = config.REPORT_SECTIONS[sec_id]
            run_counts[sec_id] = run_counts.get(sec_id, 0) + 1
            run_no = run_counts[sec_id]
            captured["context"] = None
            print(f"  [{method_name}] {i + 1}/{len(run_plan)} · {sec_id}. {title} (반복 {run_no}) 생성 중...")
            with quiet():
                content = generator_fn(sec_id, title, report_params, None)
            results.append({
                "section_id": sec_id,
                "run": run_no,
                "title": title,
                "content": content,
                "context": captured["context"] or "",
            })
    finally:
        utils.format_context = original_format_context

    return results

def evaluate_method(method_name: str, sections: List[Dict]) -> Dict:
    grounded_flags, claim_counts = [], []
    for sec in sections:
        print(f"  [{method_name}] {sec['section_id']}번 섹션 (반복 {sec['run']}) 독립 채점 중...")
        verdict = judge_grounding(sec["context"], sec["content"])
        if verdict["grounded"] is None:
            continue
        grounded_flags.append(1 if verdict["grounded"] else 0)
        claim_counts.append(len(verdict["unsupported_claims"]))
        if not verdict["grounded"]:
            for c in verdict["unsupported_claims"]:
                print(f"      - 근거 없음: {c[:80]}")

    n = len(grounded_flags)
    return {
        "n": n,
        "grounded_rate": sum(grounded_flags) / n if n else 0.0,
        "avg_unsupported_claims": sum(claim_counts) / n if n else 0.0,
    }

def print_report(legacy_result: Dict, corrective_result: Dict) -> None:
    bar = "=" * 62
    print(f"\n{bar}")
    print(f"  Corrective RAG(LangGraph) vs 기존 선형 파이프라인 - 환각 비율 비교")
    print(f"  독립 심사 모델: {JUDGE_LLM_MODEL} (그래프 내부 채점과는 별도 경로)")
    print(bar)
    print(f"  {'지표':<24}{'선형(legacy)':>16}{'Corrective RAG':>16}")
    print(f"  {'-'*24}{'-'*16:>16}{'-'*16:>16}")
    lg, cg = legacy_result["grounded_rate"], corrective_result["grounded_rate"]
    la, ca = legacy_result["avg_unsupported_claims"], corrective_result["avg_unsupported_claims"]
    print(f"  {'근거 있음 판정 비율':<24}{lg:>16.2%}{cg:>16.2%}")
    print(f"  {'섹션당 평균 근거없는 문장':<24}{la:>16.2f}{ca:>16.2f}")
    print(bar)

def cleanup():
    with quiet():
        utils.ensure_milvus_connection()
        if utility.has_collection(EVAL_COLLECTION):
            utility.drop_collection(EVAL_COLLECTION)
    config.COLLECTION_FIELD_MAPPINGS.pop(EVAL_COLLECTION, None)
    print(f"\n[cleanup] Dropped temporary collection '{EVAL_COLLECTION}'.")

if __name__ == "__main__":
    if "--yes" not in sys.argv and not confirm_cost():
        print("취소되었습니다.")
        sys.exit(0)

    if not os.path.exists(CSV_PATH):
        print(f"오류: {CSV_PATH} 를 찾을 수 없습니다. docker-compose.yml의 볼륨 마운트를 확인하세요.")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} real articles from naver_news_data.csv")
    records = build_corpus(df)
    with quiet():
        setup_eval_collection(records)
    print(f"Indexed {len(records)} chunks into temporary collection '{EVAL_COLLECTION}'.\n")

    original_collection_names = config.COLLECTION_NAMES
    config.COLLECTION_NAMES = [EVAL_COLLECTION]

    chapter = "\n\n".join(f"{k}. {v}" for k, v in sorted(config.REPORT_SECTIONS.items(), key=lambda x: x[0]))
    report_params = {
        "title": "셀트리온 기업 분석 보고서 (평가용)",
        "company": "셀트리온",
        "date": "2024년 4분기",
        "chapter": chapter,
        "indicator": "none",
        "evaluations": "",
    }

    try:
        print("=" * 62)
        print("[1/2] 선형(legacy) 파이프라인으로 섹션 생성")
        print("=" * 62)
        legacy_sections = generate_sections(
            "legacy", rag_report_pipeline._generate_report_section_legacy, report_params,
        )

        print(f"\n{'=' * 62}")
        print("[2/2] Corrective RAG(LangGraph) 파이프라인으로 섹션 생성")
        print("=" * 62)
        corrective_sections = generate_sections(
            "corrective", rag_report_pipeline._generate_report_section_graph, report_params,
        )

        print(f"\n{'=' * 62}")
        print("독립 채점 진행")
        print("=" * 62)
        legacy_result = evaluate_method("legacy", legacy_sections)
        corrective_result = evaluate_method("corrective", corrective_sections)

        print_report(legacy_result, corrective_result)
    finally:
        config.COLLECTION_NAMES = original_collection_names
        cleanup()
