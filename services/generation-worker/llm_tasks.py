# llm_tasks.py — 보고서 생성에 쓰는 LLM 호출들 (rag_server/utils.py에서 분리)
from typing import Any, Dict, List

from openai import OpenAIError

import config
import prompts # 동적 프롬프트 함수 import
from myanalyst_common import observability
from myanalyst_common.llm import get_openai_client

# --- Context Formatting Function ---
def format_context(retrieved_chunks: List[Dict[str, Any]]) -> str:
    """Formats retrieved chunks into a string for the LLM context."""
    if not retrieved_chunks:
        return ""
        
    context_str = ""
    for i, chunk in enumerate(retrieved_chunks):
        # 텍스트가 비어있는 경우 처리
        chunk_text = chunk.get('text', '')
        if not chunk_text or chunk_text.strip() == "":
            print(f"Warning: Empty text field in chunk {i+1} (ID: {chunk.get('id')})")
            continue
            
        # Include more metadata if available
        source_info = chunk.get('title') or chunk.get('source_type', chunk['collection'])
        context_str += f"--- 문서 {i+1} (ID: {chunk.get('id')}, 출처: {source_info}) ---\n"
        context_str += chunk_text + "\n\n"
    
    if not context_str.strip():
        print("Warning: All retrieved chunks had empty text fields")
        return ""
        
    return context_str.strip()


# --- LLM Interaction Functions ---
def ask_llm(query: str, context: str = "", base_prompt: str = prompts.BASE_PROMPT_TEXT, model: str = config.LLM_MODEL) -> str:
    """Sends a query and context to the LLM and returns the answer."""
    # 컨텍스트 정보가 없거나 비어있는 경우 명확한 메시지 제공
    if not context or context.strip() == "":
        context_message = """
검색된 컨텍스트가 없거나 불충분합니다. 이 경우:
1. 해당 섹션이 일반적으로 어떤 내용을 다루는지 간략히 설명할 수 있습니다.
2. 컨텍스트에 없는 정보를 임의로 생성하거나 외부 지식을 사용하지 마세요.
"""
    else:
        context_message = context
    
    full_prompt = f"""
{base_prompt}

[컨텍스트 정보]
{context_message}

[사용자 질문]
{query}

[답변 지침]
1. 컨텍스트에 관련 정보가 있으면, 그 정보만 사용하여 구체적으로 답변하세요..
2. 일반적인 업계 지식이나 추측으로 정보를 채우지 마세요.
3. 컨텍스트가 비어있거나 불충분하더라도, 컨텍스트에 없는 내용을 생성하지 마세요.

[답변]
"""
    print(f"[DEBUG] LLM 프롬프트 길이: {len(full_prompt)} 자")
    print(f"[DEBUG] LLM 모델: {model}")
    print(f"[DEBUG] 컨텍스트 길이: {len(context) if context else 0} 자")
    
    try:
        client = get_openai_client()
        with observability.time_llm_call(model, "ask_llm") as usage:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based ONLY on the provided context in Korean. You must explicitly state when information is not available. Do not use outside knowledge."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.7, # Adjust creativity
                # max_tokens=1500 # Optional: Limit response length
            )
            observability.record_usage(usage, response)
        answer = response.choices[0].message.content.strip()
        return answer
    except OpenAIError as oai_err:
        print(f"OpenAI API Error: {oai_err}")
        return f"OpenAI API 오류가 발생했습니다: {oai_err}"
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return "LLM 호출 중 오류가 발생했습니다."

def generate_keywords_for_section(section_number: str, section_title: str, company="셀트리온", date="24년 4분기") -> str:
    """Uses LLM to generate search keywords for a specific report section."""
    print(f"Generating keywords for Section {section_number}: '{section_title}'...")
    
    # 키워드 생성 실패 방지를 위한 추가 처리
    clean_section_number = section_number.replace(".", "")  # 하위 섹션 번호 표기 제거
    clean_title = section_title
    
    # 동적 프롬프트 생성 (새 함수 사용)
    keyword_prompt = prompts.create_keyword_prompt(
        section_number=clean_section_number,
        section_title=clean_title,
        company=company,
        date=date,
        top_k=config.SEARCH_TOP_K
    )
    
    print(f"[DEBUG] 키워드 생성 프롬프트: {keyword_prompt}")
    
    # Use ask_llm, but without providing external context, just the base instructions
    keywords = ask_llm(
        query=keyword_prompt,
        context="", # No external context needed for keyword generation itself
        base_prompt="", # Use the query directly as the full prompt
        model=config.KEYWORD_LLM_MODEL # Use specific model if configured
    )
    
    # 키워드 생성 실패 시 기본값 제공
    if not keywords or "오류" in keywords or "cannot" in keywords.lower():
        default_keywords = f"{company} {date} {clean_title} 실적 분석 보고서 재무 전략"
        print(f"Warning: Failed to generate keywords. Using default: {default_keywords}")
        return default_keywords
    
    print(f"Generated keywords: {keywords}")
    return keywords

def generate_summary_from_sections(combined_sections: str, company="셀트리온", date="24년 4분기", title="기업 분석 보고서") -> str:
    """Uses LLM to generate the summary from combined sections."""
    print("Generating report summary...")
    
    # 동적 요약 프롬프트 생성
    summary_prompt = prompts.create_summary_prompt(
        company=company,
        date=date,
        title=title
    )

    # The combined_sections act as the 'context' for the summary prompt
    summary = ask_llm(
        query=summary_prompt,
        context=combined_sections, # Pass the combined sections here
        base_prompt=prompts.BASE_PROMPT_TEXT, # Provide base instructions
        model=config.SUMMARY_LLM_MODEL # Use specific model if configured
    )
    print("Summary generation complete.")
    return summary

def extract_domain_specific_terms(report_text: str) -> List[Dict[str, str]]:
    """
    Uses LLM to identify and explain domain-specific terms in the report.
    
    Args:
        report_text: The full text of the generated report
        
    Returns:
        A list of dictionaries with 'term' and 'explanation' keys
    """
    print("Extracting domain-specific terms from report...")
    
    # Prepare a prompt that asks the LLM to find domain-specific terms
    prompt = f"""
    당신은 금융, 투자, 기업 분석 분야의 전문가입니다. 
    다음 기업 분석 보고서에서 일반인이 이해하기 어려운 도메인 특화 용어들을 추출하고 간결하게 설명해주세요.

    추출해야 할 용어는:
    1. 금융/회계 용어 (예: PER, EPS, 영업이익률)
    2. 산업 특화 용어 (예: 바이오시밀러, API)
    3. 투자 관련 용어 (예: 시가총액, 배당수익률)
    4. 사업 전략 용어 (예: 내재화, 합병시너지)

    다음 형식으로 JSON 배열을 반환해주세요:
    [
      {{"term": "용어1", "explanation": "자세한 설명"}},
      {{"term": "용어2", "explanation": "자세한 설명"}},
      ...
    ]

    자세한 설명의 분량에 제한은 없습니다.
    자세한 설명의 경우 일반인이 이해할 수 있도록 용어의 뜻을 쉽게 설명해주세요. 
    그러나 용어를 이해하는 데 필요한 설명을 누락하면 안됩니다. 
    특히, 기업 분석 보고서에서의 용례를 가져온 후, 해당 문장이 어떤 의미인지 자세하게 설명하는 내용을 포함해야 합니다.
    필요한 경우 예시를 들어주세요.

    단어의 개수 제한은 없습니다. 반드시 보고서에 실제로 등장하는 용어만 포함해주세요.
    일반적으로 널리 알려진 단어(예: 주식, 회사, 금융, 보건 등)는 포함하지 마세요.

    [보고서]
    {report_text}
    """
    
    try:
        # API 호출 최적화 - 보고서가 너무 길면 요약하거나 잘라서 사용
        if len(report_text) > 12000:  # 토큰 한계를 고려한 대략적인 길이
            print(f"Report too long ({len(report_text)} chars), trimming for term extraction")
            # 앞부분과 뒷부분을 균형있게 유지하면서 중간을 생략
            text_for_extraction = report_text[:6000] + "\n\n...[중간 내용 생략]...\n\n" + report_text[-6000:]
        else:
            text_for_extraction = report_text
            
        client = get_openai_client()
        with observability.time_llm_call(config.LLM_MODEL, "extract_domain_terms") as usage:
            response = client.chat.completions.create(
                model=config.LLM_MODEL,  # Use the same model as for report generation
                messages=[
                    {"role": "system", "content": "You are a financial expert who can identify domain-specific terms in corporate analysis reports. Return your response in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more deterministic results
                response_format={"type": "json_object"}  # Request JSON format
            )
            observability.record_usage(usage, response)

        result = response.choices[0].message.content.strip()
        print(f"LLM returned domain terms response of length: {len(result)}")
        
        # Parse the JSON response
        import json
        try:
            result_json = json.loads(result)
            # Extract the terms list if it's wrapped in an object
            terms_list = result_json.get("terms", result_json) if isinstance(result_json, dict) else result_json
            
            # Validate the structure - each item should have 'term' and 'explanation'
            validated_terms = []
            for item in terms_list:
                if isinstance(item, dict) and 'term' in item and 'explanation' in item:
                    validated_terms.append({
                        'term': item['term'], 
                        'explanation': item['explanation']
                    })
            
            print(f"Successfully extracted {len(validated_terms)} domain-specific terms")
            return validated_terms
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Raw response: {result[:500]}...")  # Print start of response for debugging
            return []
            
    except OpenAIError as oai_err:
        print(f"OpenAI API Error during term extraction: {oai_err}")
        return []
    except Exception as e:
        print(f"Unexpected error during term extraction: {e}")
        import traceback
        traceback.print_exc()
        return []
