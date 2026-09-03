# main.py
from fastapi import FastAPI, HTTPException, status, Path, Body, File, UploadFile, Form
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict
import time
import urllib.parse

# Import modules in the correct order to avoid circular imports
import utils  # First import utils
import crawling  # Then import crawling
from crawling import NewsItemResponse  # Import specific classes
import config  # Config import is fine
import hybrid_search  # Dense+BM25 하이브리드 검색
import rag_report_pipeline  # Import RAG pipeline last since it depends on utils

# --- FastAPI App Initialization ---
app = FastAPI(title="RAG Corporate Analysis Report Generator")


@app.on_event("startup")
async def prewarm_hybrid_search_index():
    """BM25 스파스 인덱스를 서버 기동 시 미리 구축해, 첫 보고서 생성 요청이 인덱스
    빌드 시간만큼 느려지는 걸 피한다. 실패해도 서버는 그대로 뜨고, 검색 시점에 재시도한다."""
    try:
        utils.ensure_milvus_connection()
        hybrid_search.build_bm25_index()
    except Exception as e:
        print(f"[WARN] BM25 인덱스 사전 구축 실패 (첫 검색 요청 시 재시도됩니다): {e}")

# --- Pydantic Models (for potential future request/response structure) ---
class ReportRequest(BaseModel):
    title: str  # 보고서 제목
    company: str = "셀트리온"  # 분석하고자 하는 기업, 현재는 셀트리온으로 고정
    date: str = "24년 4분기"  # 분석하고자 하는 시기, 현재는 24년 4분기로 고정
    chapter: str  # 목차의 목록, \n\n으로 구분
    indicator: str = "none"  # 보고서 생성 시 관심 지표, 현재는 none으로 고정
    evaluations: str = ""  # 섹션별 평가 기준, \n\n으로 구분

class ReportResponse(BaseModel):
    report: str
    generation_time_seconds: float
    domain_specific_terms: Optional[List[Dict[str, str]]] = None  # Added field for domain-specific terms

class NewsItem(BaseModel):
    rank: int # 순위
    title: str # 제목
    link: HttpUrl # 뉴스 링크 (Pydantic이 URL 형식 검증)
    summary: Optional[str] = None # 요약 (없을 수도 있음)
    press: Optional[str] = None # 언론사 (없을 수도 있음)
    published_info: Optional[str] = None # 발행 정보 (예: "1시간 전", "YTN", "2023.01.01.")

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

class TermInput(BaseModel):
    term: str = Field(..., description="뜻을 검색할 단어")
    explanation: Optional[str] = Field(None, description="사용자 제공 설명 (API는 이 값을 사용하지 않음)")

# 응답 본문의 각 아이템에 대한 모델 (수정됨)
class TermDefinitionOutput(BaseModel):
    term: str = Field(..., description="검색한 단어")
    definitions: List[str] = Field(..., description="네이버 사전에서 크롤링한 뜻 목록")
    source_url: Optional[HttpUrl] = Field(None, description="뜻을 가져온 검색 결과 페이지 URL") # 추가된 필드

class QuestionRequest(BaseModel):
    report: str = Field(..., description="기업 분석 보고서 내용")
    question: str = Field(..., description="보고서에 대한 질문")

class QuestionResponse(BaseModel):
    answer: str = Field(..., description="보고서 내용을 바탕으로 생성된 질문 답변")
    question: Optional[str] = Field(None, description="사용자의 질문 또는 STT로 변환된 질문 텍스트")

class AudioQuestionRequest(BaseModel):
    report: str = Field(..., description="기업 분석 보고서 내용")

# --- API Endpoint ---
@app.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(request: ReportRequest): 
    """
    Generates a corporate analysis report using RAG based on provided parameters.
    """
    print(f"Received request for /reports endpoint: {request.dict()}")
    start_api_time = time.time()

    try:
        # Ensure models are loaded and Milvus connection established
        utils.ensure_milvus_connection()

        # Call the main RAG pipeline function with request parameters
        generated_report = rag_report_pipeline.generate_full_report(
            title=request.title,
            company=request.company,
            date=request.date,
            chapter=request.chapter,
            indicator=request.indicator,
            evaluations=request.evaluations
        )

        # Extract domain-specific terms from the generated report
        print("Extracting domain-specific terms from the report...")
        domain_terms = utils.extract_domain_specific_terms(generated_report)
        
        end_api_time = time.time()
        total_api_time = end_api_time - start_api_time
        print(f"Report generation successful. Total API time: {total_api_time:.2f}s")

        return ReportResponse(
            report=generated_report,
            generation_time_seconds=round(total_api_time, 2),
            domain_specific_terms=domain_terms
        )

    except RuntimeError as e:
         # Catch critical errors like Milvus connection or model loading failures
         print(f"Runtime Error during report generation: {e}")
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
             detail=f"Internal server error during report generation: {e}",
         )
    except Exception as e:
        # Catch any other unexpected errors during the pipeline
        print(f"Unexpected Error during report generation: {e}")
        # Optionally log the full traceback here
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}",
        )

@app.get(
    "/news/{company_name}", 
    response_model=List[NewsItemResponse],  # NewsItem 대신 NewsItemResponse 사용
    summary="특정 회사의 최신 네이버 뉴스 가져오기",
    description="지정된 회사명에 대한 최신 네이버 뉴스 10개를 크롤링하여 반환합니다.",
    responses={
        200: {"description": "뉴스 기사를 성공적으로 가져왔습니다."},
        404: {"description": "해당 회사에 대한 뉴스 기사를 찾을 수 없습니다."},
        500: {"description": "내부 서버 오류 또는 크롤링 중 오류 발생."},
        503: {"description": "네이버에서 뉴스를 가져올 수 없습니다 (예: 네이버와의 네트워크 문제)."}
    }
)
async def get_company_news(
    company_name: str = Path(..., title="회사명", description="뉴스 검색 대상 회사명 (예: 삼성전자, 셀트리온).")
):
    """
    주어진 **company_name**에 대한 최신 네이버 뉴스 10개를 가져옵니다.
    - **company_name**: 회사 이름입니다.
    """
    print(f"뉴스 API 호출: 회사명 = {company_name}")  # 디버깅용 로그 추가
    
    try:
        # 회사명이 비어있는지 확인
        if not company_name or company_name.strip() == "":
            raise HTTPException(status_code=400, detail="회사명이 비어있습니다. 유효한 회사명을 입력해주세요.")
            
        news_items = crawling.crawl_naver_news_for_company(company_name, limit=10)
        
        # 디버깅용 로그 추가
        print(f"크롤링 결과: {len(news_items)}개 기사 발견")
        
        if not news_items:
            # 빈 리스트 대신 404 에러를 반환하도록 변경 (명확한 피드백을 위해)
            raise HTTPException(status_code=404, detail=f"'{company_name}'에 대한 뉴스 기사를 찾을 수 없습니다.")
        
        # NewsItem에서 NewsItemResponse로 변환
        response_items = [
            NewsItemResponse(
                title=item.title,
                link=item.link,
                summary=item.summary,
                press=item.press
            ) for item in news_items
        ]
        
        return response_items
        
    except HTTPException as http_exc:
        # HTTP 예외의 상태 코드와 세부 정보를 로깅
        print(f"HTTP 예외: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
        
    except Exception as e:
        print(f"예상치 못한 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()  # 전체 스택 트레이스 출력
        raise HTTPException(status_code=500, detail=f"'{company_name}'에 대한 뉴스 처리 중 내부 오류가 발생했습니다: {str(e)}")

@app.get(
    "/stocks/{company_name_query}",
    response_model=StockInfo,
    summary="네이버 증권에서 회사 주식 정보 크롤링 (업데이트된 선택자)",
    description="회사명을 입력받아 네이버 증권에서 해당 회사의 주가, 시가총액 등 주요 정보를 크롤링하여 반환합니다. (제공된 HTML 구조 기반으로 선택자 조정)",
    responses={
        200: {"description": "주식 정보를 성공적으로 가져왔습니다."},
        404: {"description": "해당 회사 또는 종목 정보를 찾을 수 없습니다."},
        500: {"description": "내부 서버 오류 또는 크롤링 중 오류 발생."},
        503: {"description": "네이버 증권 서버 접근에 실패했습니다."}
    }
)
async def get_stock_info_by_company_name_updated(
    company_name_query: str = Path(..., title="회사명", description="검색할 회사명 (예: 셀트리온, 삼성전자).")
):
    try:
        stock_data = crawling.get_stock_data_with_search(company_name_query)

        if not stock_data:
             raise HTTPException(status_code=404, detail=f"'{company_name_query}'에 대한 주식 정보를 구성할 수 없습니다.")
        return stock_data
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"주식 정보 API 오류 ({company_name_query}): {e}")
        import traceback
        traceback.print_exc() # 개발 중 상세 오류 확인
        raise HTTPException(status_code=500, detail=f"'{company_name_query}'의 주식 정보 처리 중 예기치 않은 내부 오류 발생.")

@app.get(
    "/stocks/{company_name_query}/chart-image",
    summary="네이버 증권에서 해당 회사의 기본 차트 이미지 가져오기",
    description="회사명을 입력받아 네이버 증권에서 해당 회사의 기본 일일 차트 이미지를 반환합니다.",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "차트 이미지를 성공적으로 가져왔습니다.",
        },
        404: {"description": "해당 회사 또는 차트 이미지를 찾을 수 없습니다."},
        500: {"description": "내부 서버 오류 또는 크롤링 중 오류 발생."},
        503: {"description": "네이버 증권 서버 또는 이미지 서버 접근에 실패했습니다."}
    }
)
async def get_stock_chart_image_api(
    company_name_query: str = Path(..., title="회사명", description="차트 이미지를 검색할 회사명 (예: 셀트리온).")
):
    try:
        return await crawling.get_chart_image_data(company_name_query)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"차트 이미지 API 오류 ({company_name_query}): {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"'{company_name_query}'의 차트 이미지 처리 중 내부 오류 발생.")

@app.post(
    "/dictionaries",
    response_model=List[TermDefinitionOutput],
    summary="여러 단어의 뜻과 출처 URL을 네이버 사전에서 크롤링",
    description="요청 본문에 제공된 단어 목록 각각에 대해 네이버 사전에서 뜻을 검색하고, 해당 검색 결과 페이지 URL과 함께 반환합니다.",
)
async def get_definitions_from_naver_dictionary_with_url(
    terms_input: List[TermInput] = Body(..., description="뜻을 검색할 단어와 사용자 제공 설명(무시됨)이 포함된 객체의 리스트")
) -> List[TermDefinitionOutput]:
    """
    입력받은 각 단어(`term`)에 대해 네이버 사전에서 뜻을 크롤링하고, 검색에 사용된 URL을 함께 반환합니다.
    요청 예시 (리스트 형태):
    ```json
    [
        { "term": "바이오시밀러", "explanation": "사용자 제공 설명 (무시됨)" },
        { "term": "R&D" }
    ]
    ```
    응답 예시:
    ```json
    [
        { 
            "term": "바이오시밀러", 
            "definitions": ["특허가 만료된 생물 의약품에 대한 복제약."], 
            "source_url": "[https://learn.dict.naver.com/search.nhn?query=%EB%B0%94%EC%9D%B4%EC%98%A4%EC%8B%9C%EB%B0%80%EB%9F%AC](https://learn.dict.naver.com/search.nhn?query=%EB%B0%94%EC%9D%B4%EC%98%A4%EC%8B%9C%EB%B0%80%EB%9F%AC)" 
        },
        { 
            "term": "R&D", 
            "definitions": ["연구 개발(Research and Development)"], 
            "source_url": "[https://learn.dict.naver.com/search.nhn?query=R%26D](https://learn.dict.naver.com/search.nhn?query=R%26D)" 
        }
    ]
    ```
    """
    if not terms_input:
        raise HTTPException(status_code=400, detail="입력된 단어 목록이 없습니다.")

    results: List[TermDefinitionOutput] = []
    for item_input in terms_input:
        try:
            definition_output = crawling.crawl_naver_dictionary_for_term(item_input.term)
            results.append(definition_output)
        except Exception as e:
            print(f"'{item_input.term}' 크롤링 중 오류: {e}")
            # search_url을 생성해서 오류 응답에도 포함
            encoded_term_for_error_url = urllib.parse.quote(item_input.term)
            error_search_url = f"https://learn.dict.naver.com/search.nhn?query={encoded_term_for_error_url}"
            results.append(TermDefinitionOutput(
                term=item_input.term, 
                definitions=[f"오류 발생: {str(e)}"], 
                source_url=error_search_url # 오류 시에도 검색 시도 URL 반환
            ))
    
    return results

@app.post(
    "/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="기업 분석 보고서 내용에 대한 질문 답변",
    description="제공된 기업 분석 보고서를 바탕으로 사용자 질문에 대한 답변을 생성합니다.",
    responses={
        200: {"description": "질문에 대한 답변이 성공적으로 생성되었습니다."},
        400: {"description": "잘못된 요청 형식 또는 내용입니다."},
        500: {"description": "서버 내부 오류 또는 LLM 처리 중 오류가 발생했습니다."}
    }
)
async def answer_report_question(request: QuestionRequest):
    """
    제공된 기업 분석 보고서 내용을 바탕으로 사용자 질문에 대한 답변을 생성합니다.
    
    - **request.report**: 기업 분석 보고서 전체 내용
    - **request.question**: 보고서에 대한 질문
    
    보고서 내용만을 기반으로 답변을 생성합니다. 보고서에 없는 내용에 대해서는
    정보가 부족하다고 명시합니다.
    """
    print(f"질문 답변 API 호출: 질문 길이 = {len(request.question)}자, 보고서 길이 = {len(request.report)}자")
    start_time = time.time()
    
    try:
        # 보고서가 너무 짧거나 비어있는 경우 체크
        if len(request.report.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효한 보고서 내용이 제공되지 않았습니다. 보고서는 최소 100자 이상이어야 합니다."
            )
            
        # 질문이 너무 짧거나 비어있는 경우 체크
        if len(request.question.strip()) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효한 질문이 제공되지 않았습니다. 질문은 최소 5자 이상이어야 합니다."
            )
            
        # 질문에 대한 답변 생성
        answer = utils.answer_question_about_report(
            question=request.question,
            report_content=request.report
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"질문 답변 생성 완료: 소요 시간 = {processing_time:.2f}초")
        
        return QuestionResponse(
            answer=answer,
            question=request.question
        )
        
    except HTTPException as http_exc:
        # HTTP 예외 그대로 전달
        raise http_exc
    except Exception as e:
        print(f"질문 답변 생성 중 예상치 못한 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"질문 처리 중 내부 오류가 발생했습니다: {str(e)}"
        )

@app.post(
    "/questions/stt",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="음성으로 입력된 질문에 대한 기업 분석 보고서 기반 답변",
    description="사용자의 음성 질문을 텍스트로 변환하고 기업 분석 보고서를 바탕으로 답변을 생성합니다.",
    responses={
        200: {"description": "질문에 대한 답변이 성공적으로 생성되었습니다."},
        400: {"description": "잘못된 요청 형식, 음성 파일 또는 보고서 내용입니다."},
        500: {"description": "서버 내부 오류, 음성 변환 중 오류 또는 LLM 처리 중 오류가 발생했습니다."}
    }
)
async def answer_speech_question(
    report: str = Form(..., description="기업 분석 보고서 내용 (JSON 문자열)"),
    audio_file: UploadFile = File(..., description="질문 음성이 담긴 오디오 파일 (mp3, wav, m4a 지원)")
):
    """
    음성 파일로 제공된 질문을 텍스트로 변환하고, 기업 분석 보고서를 바탕으로 답변을 생성합니다.
    
    - **report**: 기업 분석 보고서 전체 내용 (폼 데이터)
    - **audio_file**: 질문 음성이 담긴 오디오 파일 (mp3, wav, m4a 형식)
    
    음성을 텍스트로 변환한 후 보고서 내용을 기반으로 답변을 생성합니다.
    변환된 텍스트는 응답에 포함됩니다.
    """
    print(f"음성 질문 API 호출: 보고서 길이 = {len(report)}자, 오디오 파일명 = {audio_file.filename}")
    start_time = time.time()
    
    try:
        # 보고서 내용 검증
        if len(report.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="유효한 보고서 내용이 제공되지 않았습니다. 보고서는 최소 100자 이상이어야 합니다."
            )
            
        # 파일 확장자 확인
        file_extension = audio_file.filename.split('.')[-1].lower()
        if file_extension not in ['mp3', 'wav', 'm4a', 'mp4', 'mpeg', 'mpga', 'webm']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"지원되지 않는 오디오 파일 형식입니다. 지원되는 형식: mp3, wav, m4a, mp4, mpeg, mpga, webm"
            )
            
        # 오디오 파일 읽기
        audio_content = await audio_file.read()
        if not audio_content or len(audio_content) < 100:  # 최소 크기 체크
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="오디오 파일이 비어있거나 너무 작습니다."
            )
            
        # 음성을 텍스트로 변환
        stt_question = utils.transcribe_audio(audio_content)
        if not stt_question or len(stt_question.strip()) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="음성으로부터 텍스트를 추출할 수 없거나 질문이 너무 짧습니다."
            )
            
        print(f"음성 변환 결과: '{stt_question}'")
        
        # 변환된 텍스트로 질문 답변 생성
        answer = utils.answer_question_about_report(
            question=stt_question,
            report_content=report
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"음성 질문 처리 완료: 소요 시간 = {processing_time:.2f}초")
        
        return QuestionResponse(
            answer=answer,
            question=stt_question
        )
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"음성 질문 처리 중 예상치 못한 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"음성 질문 처리 중 내부 오류가 발생했습니다: {str(e)}"
        )

# Health check endpoint (optional but good practice)
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "ok"}

# --- Running the App (for local development) ---
if __name__ == "__main__":
    import uvicorn
    # You might need to adjust host and port depending on your environment
    # Use reload=True only for development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
