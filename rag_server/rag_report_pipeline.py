# rag_pipeline.py
import time
from typing import Dict, List, Any, Optional, Tuple
import os
import json
from datetime import datetime

# Import utility functions and config
import utils
import config
import hybrid_search
import section_checkpoints
from prompts import build_base_prompt, create_keyword_prompt, create_summary_prompt, parse_nested_chapter

# 로깅을 위한 디렉토리 설정
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def save_debug_info(section_number, section_title, keywords, retrieved_data, prompt, section_content):
    """디버깅 정보를 JSON 파일로 저장"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"section_{section_number}_{timestamp}.json"
    filepath = os.path.join(LOG_DIR, filename)
    
    # 검색 결과에서 핵심 정보만 추출 (전체 텍스트는 너무 클 수 있음)
    retrieval_summary = []
    for item in retrieved_data:
        summary = {
            "id": item.get("id"),
            "collection": item.get("collection"),
            "score": item.get("rrf_score", item.get("score")),
            "text_preview": item.get("text", "")[:200] + "..." if item.get("text") else ""
        }
        retrieval_summary.append(summary)
    
    debug_info = {
        "section": f"{section_number}. {section_title}",
        "timestamp": timestamp,
        "keywords": keywords,
        "retrieval_count": len(retrieved_data),
        "retrieval_summary": retrieval_summary,
        "prompt_preview": prompt[:1000] + "..." if len(prompt) > 1000 else prompt,
        "generated_content_preview": section_content[:1000] + "..." if len(section_content) > 1000 else section_content
    }
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(debug_info, f, ensure_ascii=False, indent=2)
        print(f"Debug info saved to {filepath}")
    except Exception as e:
        print(f"Error saving debug info: {e}")

def generate_report_section(section_number: str, section_title: str, report_params: Dict, subsections: Dict = None) -> str:
    """Generates content for a single report section using the RAG pipeline."""
    if config.CORRECTIVE_RAG_ENABLED:
        return _generate_report_section_graph(section_number, section_title, report_params, subsections)
    return _generate_report_section_legacy(section_number, section_title, report_params, subsections)


def _generate_report_section_graph(section_number: str, section_title: str, report_params: Dict, subsections: Dict = None) -> str:
    import corrective_rag_graph

    print(f"\n--- Generating Section {section_number}: {section_title} (corrective RAG graph) ---")
    start_time = time.time()

    subsection_info = ""
    if subsections and len(subsections) > 0:
        subsection_info = "이 섹션은 다음과 같은 하위 섹션을 포함하고 있습니다:\n"
        for sub_num, sub_data in subsections.items():
            subsection_info += f"  - {sub_num} {sub_data['title']}\n"
        subsection_info += "각 하위 섹션에 맞게 내용을 구성해주세요.\n"

    initial_state = {
        "section_number": section_number,
        "section_title": section_title,
        "subsection_info": subsection_info,
        "report_params": report_params,
        "keywords": "",
        "retrieved_docs": [],
        "context": "",
        "draft": "",
        "is_grounded": False,
        "grounding_feedback": "",
        "retry_count": 0,
    }

    graph = corrective_rag_graph.get_section_graph()
    final_state = graph.invoke(initial_state, config={"recursion_limit": 25})

    section_content = final_state["draft"]
    expected_heading = f"### {section_number}. {section_title}"
    if not section_content.strip().startswith(expected_heading):
        section_content = f"{expected_heading}\n\n{section_content}"

    elapsed = time.time() - start_time
    print(
        f"Section {section_number} generation finished in {elapsed:.2f}s "
        f"(grounded={final_state['is_grounded']}, retries={final_state['retry_count'] - 1})"
    )

    debug_prompt_preview = f"[keywords]\n{final_state['keywords']}\n\n[context]\n{final_state['context'][:1000]}"
    save_debug_info(
        section_number, section_title, final_state["keywords"],
        final_state["retrieved_docs"], debug_prompt_preview, section_content,
    )

    return section_content


def _generate_report_section_legacy(section_number: str, section_title: str, report_params: Dict, subsections: Dict = None) -> str:
    print(f"\n--- Generating Section {section_number}: {section_title} ---")
    start_time = time.time()

    # Extract report parameters
    title = report_params.get('title', '기업 분석 보고서')
    company = report_params.get('company', '셀트리온')
    date = report_params.get('date', '24년 4분기')
    indicator = report_params.get('indicator', 'none')
    
    print(f"[DEBUG] 섹션: {section_number}. {section_title}")
    print(f"[DEBUG] 파라미터: 제목={title}, 기업={company}, 시기={date}, 관심지표={indicator}")
    
    # 하위 섹션 정보가 있는 경우 쿼리에 포함
    subsection_info = ""
    if subsections and len(subsections) > 0:
        subsection_info = "이 섹션은 다음과 같은 하위 섹션을 포함하고 있습니다:\n"
        for sub_num, sub_data in subsections.items():
            subsection_info += f"  - {sub_num} {sub_data['title']}\n"
        subsection_info += "각 하위 섹션에 맞게 내용을 구성해주세요.\n"
        print(f"[DEBUG] 하위 섹션 정보:\n{subsection_info}")
    
    # 1. Generate Keywords using LLM with dynamic prompt
    keywords = utils.generate_keywords_for_section(
        section_number, 
        section_title,
        company=company,
        date=date
    )
    if not keywords or "오류" in keywords:
        print(f"Error generating keywords for section {section_number}. Skipping.")
        return f"### {section_number}. {section_title}\n\n키워드 생성 중 오류 발생.\n"

    # 2. Get Keyword Embedding
    print("Embedding keywords...")
    keyword_embedding = utils.get_embedding(keywords)
    if keyword_embedding is None:
        print(f"Error embedding keywords for section {section_number}. Skipping.")
        return f"### {section_number}. {section_title}\n\n키워드 임베딩 중 오류 발생.\n"
    print("Keyword embedding complete.")

    # 3. Search Milvus
    print("Searching for relevant context (hybrid: dense + BM25 + RRF)...")
    retrieved_data = hybrid_search.hybrid_search(
        query_text=keywords,
        query_vector=keyword_embedding,
        collection_names=config.COLLECTION_NAMES,
        top_k=config.SEARCH_TOP_K
    )
    if not retrieved_data:
        print("No relevant context found in Milvus. Using fallback prompt...")
        # 검색 결과가 없을 경우 최소한의 섹션 구조를 생성하는 프롬프트 전달
        context_for_llm = f"<참고: 이 주제에 대한 구체적인 자료가 충분하지 않습니다. 섹션 {section_number}. {section_title}의 적절한 구조를 갖춘 간략한 안내문을 작성해주세요.>"
    else:
        print(f"Found {len(retrieved_data)} relevant chunks.")
        # 검색 결과의 처음 3개 항목만 로그로 출력
        for i, item in enumerate(retrieved_data[:3]):
            print(f"[DEBUG] 검색결과 샘플 {i+1}:")
            print(f"  ID: {item.get('id')}")
            print(f"  Collection: {item.get('collection')}")
            print(f"  Score: {item.get('rrf_score', item.get('score'))}")
            text_preview = item.get('text', '')[:200] + "..." if len(item.get('text', '')) > 200 else item.get('text', '')
            print(f"  Text preview: {text_preview}")
        
        context_for_llm = utils.format_context(retrieved_data)

    # 4. Generate Section Content using LLM with dynamic prompt
    print("Generating section content with LLM...")
    # Construct the specific query for the LLM for this section
    user_query_for_section = f"{date} {company}의 기업 분석 보고서 중 {section_number}번인 '{section_title}'에 대해 제공된 컨텍스트 정보를 바탕으로 작성해주세요. {subsection_info}컨텍스트에 없는 내용은 절대 포함하지 마세요."
    
    # Build a dynamic base prompt that includes report parameters
    dynamic_base_prompt = build_base_prompt(
        title=title,
        company=company,
        date=date,
        chapter=report_params.get('chapter', ''),
        indicator=indicator,
        evaluations=report_params.get('evaluations', '')
    )

    print(f"[DEBUG] LLM 쿼리: {user_query_for_section[:200]}...")
    
    # 프롬프트 전문을 로그 파일에 저장
    full_prompt = f"""
{dynamic_base_prompt}

[컨텍스트 정보]
{context_for_llm if context_for_llm else "제공된 컨텍스트 정보가 없습니다."}

[사용자 질문]
{user_query_for_section}

[답변 지침]
컨텍스트 정보가 충분치 않더라도 섹션 제목에 맞는 적절한 구조의 내용을 생성해 주세요.
"""
    
    # 검색 결과가 없더라도 최소한의 내용 생성
    section_content = utils.ask_llm(
        query=user_query_for_section,
        context=context_for_llm,
        base_prompt=dynamic_base_prompt,
        model=config.LLM_MODEL
    )

    end_time = time.time()
    print(f"Section {section_number} generation finished in {end_time - start_time:.2f} seconds.")

    # Ensure the output starts with the correct heading format
    expected_heading = f"### {section_number}. {section_title}"
    if not section_content.strip().startswith(expected_heading):
         # Prepend the heading if the LLM didn't include it reliably
         section_content = f"{expected_heading}\n\n{section_content}"
    
    # 디버깅 정보 저장
    save_debug_info(section_number, section_title, keywords, retrieved_data, full_prompt, section_content)
    
    # 최종 생성 결과 미리보기 출력
    content_preview = section_content[:500] + "..." if len(section_content) > 500 else section_content
    print(f"[DEBUG] 생성된 내용 미리보기:\n{content_preview}")

    return section_content


def generate_full_report(title="기업 분석 보고서", company="셀트리온", date="24년 4분기",
                        chapter="", indicator="none", evaluations="",
                        generation_job_id: Optional[str] = None) -> str:
    """
    Orchestrates the generation of the full multi-section report.

    Args:
        title: 보고서 제목
        company: 분석 대상 기업
        date: 분석 시기 (예: '24년 4분기')
        chapter: 목차 목록 (중첩 구조 가능)
        indicator: 관심 지표 (없으면 'none')
        evaluations: 섹션별 평가 기준 (\n\n으로 구분)
        generation_job_id: 지정하면 섹션별 생성 결과를 체크포인트로 저장해, 이 함수가
            중간에 죽어도 재시도 시 이미 만든 섹션은 다시 생성하지 않는다.
    """
    full_report_start_time = time.time()
    print(f"Starting full report generation for '{title}' about {company} ({date})...")
    
    # 파라미터를 사전에 저장하여 기능 간에 전달
    report_params = {
        'title': title,
        'company': company,
        'date': date,
        'chapter': chapter,
        'indicator': indicator,
        'evaluations': evaluations
    }

    # 중첩 구조를 가진 목차 파싱
    sections, main_section_nums, summary_key = parse_nested_chapter(chapter)
    
    # 파싱 결과 상세 로깅
    print(f"Parsed sections structure: {sections}")
    print(f"Main section numbers (no duplicates): {main_section_nums}")
    print(f"Summary section key: {summary_key}")
    
    # 중복 섹션 번호 확인
    section_count = {}
    for num in main_section_nums:
        section_count[num] = section_count.get(num, 0) + 1
    
    duplicate_sections = [num for num, count in section_count.items() if count > 1]
    if duplicate_sections:
        print(f"Warning: Duplicate section numbers detected: {duplicate_sections}")

    # 기본 섹션 구조 처리 (파싱된 목차가 없는 경우)
    if not sections:
        sections = {
            num: {"title": title, "subsections": {}} 
            for num, title in config.REPORT_SECTIONS.items()
        }
        main_section_nums = config.SECTION_GENERATION_ORDER
        summary_key = config.SUMMARY_SECTION_KEY
    
    # 컨텐츠 생성을 위한 섹션 순서 설정 (요약 제외 및 중복 제거)
    generation_order = []
    for num in main_section_nums:
        if num != summary_key and num not in generation_order:
            generation_order.append(num)
    
    print(f"Generation order (after processing): {generation_order}")
    
    generated_sections = {}
    if generation_job_id:
        generated_sections.update(section_checkpoints.load_sections(generation_job_id))
        if generated_sections:
            print(f"[checkpoint] job={generation_job_id}: {sorted(generated_sections)} 섹션을 이전 시도에서 복원")

    # Generate content sections first (excluding summary)
    processed_sections = set()  # 이미 처리된 섹션을 추적하기 위한 세트
    
    for section_key in generation_order:
        if section_key in sections and section_key not in processed_sections:
            # 이미 처리된 섹션으로 표시
            processed_sections.add(section_key)
            
            section_data = sections[section_key]
            section_title = section_data["title"]
            subsections = section_data.get("subsections", {})
            
            print(f"\nProcessing main section {section_key}: {section_title}")
            
            # 중복 섹션 생성 방지: 이미 생성된 섹션은 건너뛴다
            if section_key in generated_sections:
                print(f"Section {section_key} already generated. Skipping.")
                continue
            
            # 해당 섹션 생성 (하위 섹션 정보 포함)
            generated_content = generate_report_section(
                section_key,
                section_title,
                report_params,
                subsections
            )
            generated_sections[section_key] = generated_content
            if generation_job_id:
                section_checkpoints.save_section(generation_job_id, section_key, generated_content)
        else:
             print(f"Warning: Section key '{section_key}' not found in sections mapping or already processed.")

    # Combine sections for summary context
    print("\nCombining generated sections for summary context...")
    combined_context_for_summary = "\n\n".join(
        generated_sections[key] for key in generation_order if key in generated_sections
    )

    # Generate Summary section
    if summary_key and summary_key in sections and summary_key in generated_sections:
        print(f"Section {summary_key} (Summary) already generated. Skipping.")
    elif summary_key and summary_key in sections:
        summary_section_title = sections[summary_key]["title"]
        print(f"\n--- Generating Section {summary_key}: {summary_section_title} ---")
        summary_start_time = time.time()

        # 동적으로 생성된 요약 프롬프트 사용
        summary_content = utils.generate_summary_from_sections(
            combined_context_for_summary,
            company=company,
            date=date,
            title=title
        )

        summary_end_time = time.time()
        print(f"Section {summary_key} (Summary) generation finished in {summary_end_time - summary_start_time:.2f} seconds.")

        # Ensure summary output starts with the correct heading
        expected_summary_heading = f"### {summary_key}. {summary_section_title}"
        if not summary_content.strip().startswith(expected_summary_heading):
             summary_content = f"{expected_summary_heading}\n\n{summary_content}"
        generated_sections[summary_key] = summary_content
        if generation_job_id:
            section_checkpoints.save_section(generation_job_id, summary_key, summary_content)
    else:
        print("Warning: No summary section defined.")

    # Combine all sections in the final order
    print("\nCombining all sections into the final report...")
    final_report_parts = []
    
    # 요약 섹션을 먼저 추가 (있는 경우)
    if summary_key in generated_sections:
        final_report_parts.append(generated_sections[summary_key])
    
    # 요약을 제외한 나머지 섹션들을 추가
    for section_key in generation_order:
        if section_key in generated_sections:
            final_report_parts.append(generated_sections[section_key])

    final_report = "\n\n".join(final_report_parts)

    full_report_end_time = time.time()
    total_time = full_report_end_time - full_report_start_time
    print(f"\nFull report generation completed in {total_time:.2f} seconds.")

    if generation_job_id:
        section_checkpoints.clear_job(generation_job_id)

    return final_report

# Example usage (optional, for testing this module directly)
if __name__ == "__main__":
    sample_chapter = """1. 보고서 요약 (Executive Summary)

2. 2024년 4분기 실적 분석
  2.1 매출 분석
  2.2 비용 분석

3. 주요 사업 및 제품 동향
  3.1 제품 관련 소식
  3.2 R&D 및 파이프라인
  3.3 CMO 사업
  3.4 기타 사업

4. 시장 환경 및 전략 방향

5. 향후 전망 (공식 발표 기반)

6. 기타 참고사항"""
    
    sample_evaluations = """- 핵심 내용 반영도: 보고서 본문의 핵심 내용을 요약하고 있는가?
- 정확성 및 일관성: 요약된 내용이 컨텍스트와 일치하는가?

- 실적 요인 분석 정확성: 실적 변동 요인 설명이 컨텍스트와 일치하는가?
- 실적 요인 분석 완전성: 주요 실적 변동 요인을 충분히 다루고 있는가?

- 정보 정확성: 제품 동향, R&D 정보가 컨텍스트와 일치하는가?
- 정보 완전성: 중요 업데이트 사항을 누락 없이 포함했는가?"""
    
    report = generate_full_report(
        title="셀트리온 4분기 실적 분석", 
        company="셀트리온", 
        date="24년 4분기",
        chapter=sample_chapter,
        evaluations=sample_evaluations
    )
    print("\n--- FINAL GENERATED REPORT ---")
    print(report)