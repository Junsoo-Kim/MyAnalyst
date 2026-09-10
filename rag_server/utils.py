# utils.py
import torch
from transformers import AutoTokenizer, AutoModel
from pymilvus import connections, Collection, utility, MilvusException
from openai import OpenAI, OpenAIError
import numpy as np
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import tempfile
import os

# Import config variables
import config
import prompts # 동적 프롬프트 함수 import
import observability

# --- Global Variables for Model & Tokenizer ---
# Load models only once when the module is imported
tokenizer: Optional[AutoTokenizer] = None
embedding_model: Optional[AutoModel] = None
device: Optional[torch.device] = None

class StockInfo(BaseModel):
    retrieved_at: str  # API 호출 시각 (정보 가져온 시간)
    data_timestamp_info: Optional[str] = None # 네이버 증권 페이지에 표시된 데이터 기준 시각 정보
    company_name: str
    stock_code: str
    market_type: Optional[str] = None # 코스피/코스닥
    item_main_url: Optional[str] = None # 네이버 증권에서 종목 정보를 크롤링한 페이지 URL
    
    current_price: Optional[str] = None
    price_change: Optional[str] = None  # 전일비 (부호 포함, 예: "+1,100" 또는 "-500")
    change_rate: Optional[str] = None  # 등락률 (부호 포함, 예: "+0.71%" 또는 "-0.50%")
    
    yesterday_close: Optional[str] = None # 전일 종가
    open_price: Optional[str] = None # 시가
    high_price: Optional[str] = None # 고가
    low_price: Optional[str] = None # 저가
    upper_limit_price: Optional[str] = None # 상한가
    lower_limit_price: Optional[str] = None # 하한가
    
    volume: Optional[str] = None  # 거래량 (주)
    volume_value: Optional[str] = None  # 거래대금 (단위 포함, 예: "3,791백만")
    
    market_cap: Optional[str] = None  # 시가총액 (단위 포함, 예: "34조 8,350억원")
    market_cap_rank: Optional[str] = None # 시가총액 순위 (예: "코스피 11위")
    shares_outstanding: Optional[str] = None # 상장주식수
    
    foreign_ownership_ratio: Optional[str] = None # 외국인소진율 (%)
    
    fifty_two_week_high: Optional[str] = None
    fifty_two_week_low: Optional[str] = None
    
    per_info: Optional[str] = None # PER (배) (예: "84.31배 (2024.12)")
    eps_info: Optional[str] = None # EPS (원) (예: "1,855원 (2024.12)")
    
    estimated_per_info: Optional[str] = None # 추정 PER (배)
    estimated_eps_info: Optional[str] = None # 추정 EPS (원)

    pbr_info: Optional[str] = None # PBR (배) (예: "1.93배 (2024.12)")
    bps_info: Optional[str] = None # BPS (원) (예: "80,940원 (2024.12)")
    
    dividend_yield_info: Optional[str] = None # 배당수익률 (%) (예: "0.46% (2024.12)")
    
    industry_per_info: Optional[str] = None # 동일업종 PER

def initialize_models():
    """Initializes the tokenizer and embedding model."""
    global tokenizer, embedding_model, device
    if tokenizer is None or embedding_model is None:
        print("Initializing embedding model and tokenizer...")
        try:
            tokenizer = AutoTokenizer.from_pretrained(config.EMBEDDING_MODEL_NAME)
            embedding_model = AutoModel.from_pretrained(config.EMBEDDING_MODEL_NAME)
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            embedding_model.to(device)
            embedding_model.eval() # Set to evaluation mode
            print(f"Embedding models initialized on device: {device}")
        except Exception as e:
            print(f"Fatal Error initializing embedding models: {e}")
            # Exit or raise a critical error if models can't load
            raise RuntimeError(f"Could not initialize embedding models: {e}")

# Ensure models are initialized when this module is loaded
initialize_models()

# --- Milvus Connection Management ---
def ensure_milvus_connection():
    """Connects to Milvus if not already connected."""
    if not connections.has_connection("default"):
        print(f"Connecting to Milvus at {config.MILVUS_HOST}:{config.MILVUS_PORT}...")
        try:
            connections.connect("default", host=config.MILVUS_HOST, port=config.MILVUS_PORT)
            print("Successfully connected to Milvus.")
        except Exception as e:
            print(f"Fatal Error connecting to Milvus: {e}")
            # Exit or raise a critical error if connection fails
            raise RuntimeError(f"Could not connect to Milvus: {e}")

# Call this early, e.g., in main.py on startup or here directly
# ensure_milvus_connection() # Connect on module load

# --- Embedding Function ---
def mean_pooling(model_output, attention_mask):
    """Mean Pooling helper function."""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    return sum_embeddings / sum_mask

def get_embedding(text: str) -> Optional[np.ndarray]:
    """Generates an embedding vector for the given text."""
    if not tokenizer or not embedding_model or not device:
        print("Error: Embedding models not initialized.")
        return None
    try:
        encoded_input = tokenizer(
            text, padding=True, truncation=True, max_length=512, return_tensors='pt'
        ).to(device)
        with torch.no_grad():
            model_output = embedding_model(**encoded_input)
        embedding = mean_pooling(model_output, encoded_input['attention_mask'])
        return embedding.cpu().numpy().flatten() # Return as NumPy array
    except Exception as e:
        print(f"Error generating embedding for text '{text[:50]}...': {e}")
        return None

# --- Milvus Search Function ---
def search_milvus(query_vector: np.ndarray, collection_names_list: List[str], top_k_total: int) -> List[Dict[str, Any]]:
    """Searches multiple Milvus collections and returns merged, sorted results."""
    ensure_milvus_connection() # Ensure connection before searching
    all_retrieved_chunks = []
    query_list = [query_vector.tolist()] # Milvus search expects a list of vectors

    for c_name in collection_names_list:
        print(f"\nSearching in collection: '{c_name}'...")
        if not utility.has_collection(c_name):
            print(f"  Warning: Collection '{c_name}' does not exist. Skipping.")
            continue

        if c_name not in config.COLLECTION_FIELD_MAPPINGS:
            print(f"  Warning: Field mapping for collection '{c_name}' not found in config. Skipping.")
            continue

        mapping = config.COLLECTION_FIELD_MAPPINGS[c_name]
        output_fields = mapping["output_fields"]
        text_field = mapping["text_field"]

        try:
            collection = Collection(c_name)
            # Ensure collection is loaded before searching
            if not utility.load_state(c_name) == "Loaded":
                 print(f"  Loading collection '{c_name}'...")
                 collection.load()
                 utility.wait_for_loading_complete(c_name)
                 print(f"  Collection '{c_name}' loaded.")
            else:
                 print(f"  Collection '{c_name}' is already loaded.")

            print(f"  Executing search with top_k={top_k_total}...")
            with observability.time_milvus_search(c_name):
                search_results = collection.search(
                    data=query_list,
                    anns_field="embedding", # Assuming the vector field is named 'embedding'
                    param=config.SEARCH_PARAMS,
                    limit=top_k_total, # Fetch enough to sort later
                    output_fields=output_fields
                )
            print(f"  Search completed for '{c_name}'. Processing results...")

            if search_results and search_results[0]:
                for hit in search_results[0]:
                    try:
                        # 디버깅을 위한 로깅 추가
                        print(f"  Processing hit ID: {hit.id}")
                        entity_data = hit.entity.to_dict()
                        
                        # 엔티티 데이터 로깅 (처음 5개 필드만)
                        print(f"  Entity data keys: {list(entity_data.keys())[:5]}")
                        print(f"  Text field name: {text_field}")
                        
                        # 텍스트 필드가 없는 경우 직접 쿼리
                        if text_field not in entity_data or not entity_data.get(text_field):
                            print(f"  Text field '{text_field}' not found in entity or empty. Trying direct query...")
                            
                            # ID로 직접 쿼리하여 모든 필드 가져오기
                            query_result = collection.query(
                                expr=f"id == {hit.id}",
                                output_fields=["*"],
                                limit=1
                            )
                            
                            if query_result and len(query_result) > 0:
                                direct_data = query_result[0]
                                print(f"  Direct query result keys: {list(direct_data.keys())[:5]}")

                                entity_data.update(direct_data)
                                if text_field in entity_data and entity_data.get(text_field):
                                    print(f"  Text retrieved from direct query: {entity_data[text_field][:50]}...")
                                else:
                                    print(f"  Warning: Text field '{text_field}' still not found after direct query")
                            else:
                                print(f"  Warning: No results from direct query for ID {hit.id}")
                        
                        # 텍스트 값 확인 로깅
                        text_value = entity_data.get(text_field, "")
                        print(f"  Text value type: {type(text_value)}, empty: {not bool(text_value)}")
                        if text_value:
                            print(f"  Text preview: {text_value[:50]}...")
                        else:
                            print(f"  Warning: Empty text for ID {hit.id}")
                                                        
                        chunk_data = {
                            "collection": c_name,
                            "id": hit.id,
                            "score": hit.distance,
                            "source_type": c_name, # Default source type
                            "text": entity_data.get(text_field, "") # Get the main text
                        }
                        # Add other metadata fields specified in output_fields
                        for field in output_fields:
                            if field != text_field and field in entity_data:
                                chunk_data[field] = entity_data[field]
                            # Handle potential default value overrides if schema had source_type
                            # if field == "source_type" and "source_type" in entity_data:
                            #    chunk_data["source_type"] = entity_data["source_type"]

                        # 디버깅용 로깅 추가
                        print(f"  Final chunk data: id={chunk_data['id']}, has_text={bool(chunk_data['text'])}")
                        all_retrieved_chunks.append(chunk_data)
                    except Exception as process_err:
                        print(f"  Warning: Error processing hit ID {getattr(hit, 'id', 'N/A')} in '{c_name}': {process_err}")
                        import traceback
                        traceback.print_exc()
                        continue # Skip to next hit

                print(f"  Added {len(search_results[0])} results from '{c_name}'.")
            else:
                 print(f"  No results found in '{c_name}'.")

        except MilvusException as me:
            print(f"  Milvus error searching collection '{c_name}': {me}")
        except Exception as search_err:
            print(f"  Unexpected error searching collection '{c_name}': {search_err}")
            import traceback
            traceback.print_exc()

    # Sort all collected chunks by score (ascending for L2 distance) and limit
    if all_retrieved_chunks:
        all_retrieved_chunks.sort(key=lambda x: x['score'])
        print(f"\nTotal results from all collections: {len(all_retrieved_chunks)}")
        final_chunks = all_retrieved_chunks[:top_k_total]
        print(f"Returning top {len(final_chunks)} overall results.")
        
        # 로깅: 텍스트 없는 결과 카운트
        empty_text_count = sum(1 for chunk in final_chunks if not chunk.get('text'))
        if empty_text_count > 0:
            print(f"Warning: {empty_text_count} of {len(final_chunks)} results have empty text fields")
        
        # 첫 번째 결과의 텍스트 샘플 확인
        if final_chunks and final_chunks[0].get('text'):
            print(f"Sample text from first result: {final_chunks[0]['text'][:100]}...")
        
        return final_chunks
    else:
        print("\nNo relevant chunks found across all collections.")
        return []

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

def get_openai_client() -> OpenAI:
    return OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)


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
<<<<<<< HEAD
        client = OpenAI(api_key=config.OPENAI_API_KEY)
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
=======
        client = get_openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that answers questions based ONLY on the provided context in Korean. You must explicitly state when information is not available. Do not use outside knowledge."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7, # Adjust creativity
            # max_tokens=1500 # Optional: Limit response length
        )
>>>>>>> 71624a165d407f6764b539c319e0702d599ffcc0
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
            
<<<<<<< HEAD
        client = OpenAI(api_key=config.OPENAI_API_KEY)
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

=======
        client = get_openai_client()
        response = client.chat.completions.create(
            model=config.LLM_MODEL,  # Use the same model as for report generation
            messages=[
                {"role": "system", "content": "You are a financial expert who can identify domain-specific terms in corporate analysis reports. Return your response in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower temperature for more deterministic results
            response_format={"type": "json_object"}  # Request JSON format
        )
        
>>>>>>> 71624a165d407f6764b539c319e0702d599ffcc0
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

def answer_question_about_report(question: str, report_content: str) -> str:
    """
    기업 분석 보고서 내용을 바탕으로 사용자 질문에 대한 답변을 생성합니다.
    
    Args:
        question: 사용자 질문
        report_content: 기업 분석 보고서 전체 내용
        
    Returns:
        질문에 대한 답변
    """
    print(f"보고서 기반 질문 응답 생성 시작: 질문 = '{question}'")
    
    # API 호출 최적화 - 보고서가 너무 길면 중요 부분만 추출하여 사용
    if len(report_content) > 12000:  
        print(f"보고서가 너무 깁니다 ({len(report_content)}자). 응답 생성을 위해 적절히 자릅니다.")
        # 앞부분(목차와 요약 포함)과 뒷부분을 균형있게 유지
        report_for_query = report_content[:7000] + "\n\n...[중간 내용 생략]...\n\n" + report_content[-5000:]
    else:
        report_for_query = report_content
        
    # 질문 응답을 위한 프롬프트 구성
    prompt = f"""
당신은 기업 분석 보고서를 바탕으로 질문에 답변하는 전문가입니다.
다음은 기업 분석 보고서 내용입니다:

{report_for_query}

위 보고서를 바탕으로 다음 질문에 답변해 주세요:

[질문]
{question}

[답변 지침]
1. 보고서 내용을 바탕으로 기업의 상황, 실적, 전망 등에 대해 객관적으로 답변하세요.
2. 보고서에 포함된 정보를 최대한 활용하여 답변하세요. 필요한 경우 외부 지식을 사용할 수 있습니다.
3. 답변은 친절하고 명확하게 작성해주세요. 답변의 분량에 제한은 없습니다.
4. 보고서의 내용과 반대되는 내용을 주장하거나 당신의 개인적인 의견을 포함하지 마세요.
"""
    
    try:
<<<<<<< HEAD
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        with observability.time_llm_call(config.LLM_MODEL, "answer_question") as usage:
            response = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "당신은 기업 분석 보고서를 바탕으로 질문에 정확하게 답변하는 전문가입니다. 오직 보고서에 포함된 정보만을 사용하여 답변하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,  # 응답의 일관성을 위해 낮은 온도 사용
            )
            observability.record_usage(usage, response)

=======
        client = get_openai_client()
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": "당신은 기업 분석 보고서를 바탕으로 질문에 정확하게 답변하는 전문가입니다. 오직 보고서에 포함된 정보만을 사용하여 답변하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,  # 응답의 일관성을 위해 낮은 온도 사용
        )
        
>>>>>>> 71624a165d407f6764b539c319e0702d599ffcc0
        answer = response.choices[0].message.content.strip()
        return answer
        
    except OpenAIError as oai_err:
        print(f"OpenAI API Error: {oai_err}")
        return f"질문에 대한 답변을 생성하는 중 오류가 발생했습니다: {oai_err}"
        
    except Exception as e:
        print(f"질문 응답 생성 중 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        return "질문 처리 중 내부 오류가 발생했습니다. 다시 시도해 주세요."

def get_text_from_spans(element):
    """span으로 나뉘어진 숫자/텍스트를 합쳐서 반환"""
    if not element:
        return None
    return "".join(s.get_text(strip=True) for s in element.find_all(['span', 'em'], recursive=False) if s.get_text(strip=True)) \
           or element.get_text(strip=True)

def get_safe_text(element, default_value=None):
    """BeautifulSoup 요소에서 안전하게 텍스트 추출"""
    if element:
        return element.get_text(strip=True)
    return default_value

def clean_price_data(text):
    """가격/숫자 데이터에서 쉼표 제거 및 공백 제거"""
    if text is None:
        return None
    return text.replace(",", "").strip()

def transcribe_audio(audio_content: bytes) -> str:
    """
    OpenAI의 Whisper API를 사용하여 오디오 파일을 텍스트로 변환합니다.
    
    Args:
        audio_content: 오디오 파일의 바이너리 데이터
        
    Returns:
        변환된 텍스트
    """
    print("오디오 변환 시작...")
    
    if not audio_content:
        print("오디오 내용이 비어있습니다.")
        return ""
    
    try:
        # 임시 파일로 오디오 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio:
            temp_audio.write(audio_content)
            temp_audio_path = temp_audio.name
            
        print(f"임시 오디오 파일 저장됨: {temp_audio_path} (크기: {len(audio_content)} 바이트)")
        
        try:
            client = get_openai_client()
            
            with open(temp_audio_path, "rb") as audio_file:
                print("Whisper API 호출 중...")
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ko"  # 한국어로 설정
                )
                
            transcribed_text = response.text
            print(f"음성 변환 완료: {len(transcribed_text)}자")
            return transcribed_text
            
        finally:
            # 임시 파일 삭제
            try:
                os.unlink(temp_audio_path)
                print(f"임시 오디오 파일 삭제됨: {temp_audio_path}")
            except Exception as e:
                print(f"임시 파일 삭제 실패: {e}")
        
    except OpenAIError as oai_err:
        print(f"OpenAI Whisper API 오류: {oai_err}")
        raise Exception(f"음성 변환 중 오류가 발생했습니다: {oai_err}")
    except Exception as e:
        print(f"음성 변환 중 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"음성 변환 처리 중 오류: {e}")


