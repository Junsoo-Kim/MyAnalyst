import json
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph
from openai import OpenAI

import config
import hybrid_search
import utils
from prompts import build_base_prompt

class SectionState(TypedDict):
    section_number: str
    section_title: str
    subsection_info: str
    report_params: Dict[str, Any]
    keywords: str
    retrieved_docs: List[Dict[str, Any]]
    context: str
    draft: str
    is_grounded: bool
    grounding_feedback: str
    retry_count: int

def _grader_client() -> OpenAI:
    return utils.get_openai_client()

def _grade_documents_batch(section_title: str, keywords: str, docs: List[Dict[str, Any]]) -> List[bool]:
    if not docs:
        return []

    numbered = "\n\n".join(f"[{i}] {d.get('text', '')[:500]}" for i, d in enumerate(docs))
    prompt = f"""당신은 기업 분석 보고서용 문서 관련성 평가자입니다.
'{section_title}' 섹션을 작성하기 위해 검색 키워드 "{keywords}"로 찾은 문서 후보입니다.

각 문서가 이 섹션을 작성하는 데 실제로 쓸모 있는지 판단하세요. 주제가 다르거나 노이즈인 문서는 제외하세요.

[문서 후보]
{numbered}

다음 JSON 형식으로만 답하세요: {{"relevant_indices": [0, 2, 3]}}
"""
    try:
        response = _grader_client().chat.completions.create(
            model=config.GRADER_LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a strict relevance grader. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        relevant = set(result.get("relevant_indices", []))
    except Exception as e:
        print(f"[WARN] 문서 관련성 채점 실패, 전체 문서를 통과시킵니다(안전 폴백): {e}")
        relevant = set(range(len(docs)))

    return [i in relevant for i in range(len(docs))]

def _grade_hallucination(context: str, draft: str) -> Dict[str, Any]:
    prompt = f"""당신은 기업 분석 보고서의 사실 검증 담당자입니다.
아래 [생성된 내용]이 [컨텍스트]에 실제로 근거하는지 판단하세요.
컨텍스트에 없는 수치, 사실, 주장이 포함되어 있으면 근거가 없는 것입니다.

[컨텍스트]
{context[:8000]}

[생성된 내용]
{draft}

다음 JSON 형식으로만 답하세요:
{{"grounded": true 또는 false, "feedback": "근거가 부족하면 어떤 부분이 문제이고 어떤 정보를 더 찾아야 하는지 한두 문장"}}
"""
    try:
        response = _grader_client().chat.completions.create(
            model=config.GRADER_LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a strict factual grounding grader. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        return {"grounded": bool(result.get("grounded", True)), "feedback": result.get("feedback", "")}
    except Exception as e:
        print(f"[WARN] 환각 채점 실패, 근거 있음으로 간주합니다(fail-open): {e}")
        return {"grounded": True, "feedback": f"채점 실패: {e}"}

def _rewrite_search_query(original_keywords: str, section_title: str, feedback: str) -> str:
    prompt = f"""검색 키워드 "{original_keywords}"로 '{section_title}' 섹션을 작성했지만,
다음 이유로 컨텍스트 근거가 부족하다고 판단되었습니다:
{feedback}

이 문제를 보완할 새로운 검색 키워드를 만들어주세요. 기존 키워드와 겹치지 않는, 더 구체적이거나
다른 각도의 표현을 쓰세요. 키워드만 한 줄로 답하세요 (설명 없이).
"""
    try:
        rewritten = utils.ask_llm(query=prompt, context="", base_prompt="", model=config.KEYWORD_LLM_MODEL)
        rewritten = rewritten.strip()
        return rewritten if rewritten and "오류" not in rewritten else original_keywords
    except Exception as e:
        print(f"[WARN] 쿼리 재작성 실패, 기존 키워드를 재사용합니다: {e}")
        return original_keywords

def node_generate_keywords(state: SectionState) -> Dict[str, Any]:
    params = state["report_params"]
    keywords = utils.generate_keywords_for_section(
        state["section_number"], state["section_title"],
        company=params.get("company", ""), date=params.get("date", ""),
    )
    return {"keywords": keywords}

def node_retrieve(state: SectionState) -> Dict[str, Any]:
    embedding = utils.get_embedding(state["keywords"])
    if embedding is None:
        print(f"[WARN] 임베딩 생성 실패 (section {state['section_number']}) - 검색 결과 없음으로 처리")
        return {"retrieved_docs": []}

    docs = hybrid_search.hybrid_search(
        query_text=state["keywords"],
        query_vector=embedding,
        collection_names=config.COLLECTION_NAMES,
        top_k=config.SEARCH_TOP_K,
    )
    return {"retrieved_docs": docs}

def node_grade_documents(state: SectionState) -> Dict[str, Any]:
    docs = state["retrieved_docs"]
    if not docs:
        fallback = (
            f"<참고: 이 주제에 대한 구체적인 자료가 충분하지 않습니다. 섹션 {state['section_number']}. "
            f"{state['section_title']}의 적절한 구조를 갖춘 간략한 안내문을 작성해주세요.>"
        )
        return {"retrieved_docs": [], "context": fallback}

    relevance = _grade_documents_batch(state["section_title"], state["keywords"], docs)
    graded = [d for d, keep in zip(docs, relevance) if keep]

    if not graded:
        fallback = (
            f"<참고: 검색된 문서가 있었지만 섹션 {state['section_number']}. {state['section_title']}과(와) "
            f"관련성이 낮아 모두 제외되었습니다. 적절한 구조를 갖춘 간략한 안내문을 작성해주세요.>"
        )
        return {"retrieved_docs": [], "context": fallback}

    return {"retrieved_docs": graded, "context": utils.format_context(graded)}

def node_generate_section(state: SectionState) -> Dict[str, Any]:
    params = state["report_params"]
    dynamic_base_prompt = build_base_prompt(
        title=params.get("title", "기업 분석 보고서"),
        company=params.get("company", ""),
        date=params.get("date", ""),
        chapter=params.get("chapter", ""),
        indicator=params.get("indicator", "none"),
        evaluations=params.get("evaluations", ""),
    )
    user_query = (
        f"{params.get('date', '')} {params.get('company', '')}의 기업 분석 보고서 중 "
        f"{state['section_number']}번인 '{state['section_title']}'에 대해 제공된 컨텍스트 정보를 "
        f"바탕으로 작성해주세요. {state.get('subsection_info', '')}컨텍스트에 없는 내용은 절대 포함하지 마세요."
    )

    content = utils.ask_llm(
        query=user_query, context=state["context"], base_prompt=dynamic_base_prompt, model=config.LLM_MODEL,
    )
    return {"draft": content, "retry_count": state["retry_count"] + 1}

def node_grade_hallucination(state: SectionState) -> Dict[str, Any]:
    if state["context"].strip().startswith("<참고:"):
        return {"is_grounded": True, "grounding_feedback": ""}

    verdict = _grade_hallucination(state["context"], state["draft"])
    return {"is_grounded": verdict["grounded"], "grounding_feedback": verdict["feedback"]}

def route_after_grading(state: SectionState) -> str:
    if state["is_grounded"]:
        return "end"
    if state["retry_count"] >= config.MAX_GROUNDING_RETRIES:
        print(
            f"[WARN] Section {state['section_number']}: 재시도 {state['retry_count']}회 후에도 "
            f"근거 부족 판정 - 마지막 초안을 그대로 사용합니다. feedback={state['grounding_feedback']}"
        )
        return "end"
    return "retry"

def node_rewrite_query(state: SectionState) -> Dict[str, Any]:
    new_keywords = _rewrite_search_query(state["keywords"], state["section_title"], state["grounding_feedback"])
    print(f"[Corrective RAG] Section {state['section_number']} 쿼리 재작성: '{state['keywords']}' -> '{new_keywords}'")
    return {"keywords": new_keywords}

_compiled_graph = None

def get_section_graph():
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    graph = StateGraph(SectionState)
    graph.add_node("generate_keywords", node_generate_keywords)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("grade_documents", node_grade_documents)
    graph.add_node("generate_section", node_generate_section)
    graph.add_node("grade_hallucination", node_grade_hallucination)
    graph.add_node("rewrite_query", node_rewrite_query)

    graph.set_entry_point("generate_keywords")
    graph.add_edge("generate_keywords", "retrieve")
    graph.add_edge("retrieve", "grade_documents")
    graph.add_edge("grade_documents", "generate_section")
    graph.add_edge("generate_section", "grade_hallucination")
    graph.add_conditional_edges(
        "grade_hallucination", route_after_grading, {"retry": "rewrite_query", "end": END},
    )
    graph.add_edge("rewrite_query", "retrieve")

    _compiled_graph = graph.compile()
    return _compiled_graph
