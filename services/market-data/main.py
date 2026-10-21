# main.py — market-data-service: 뉴스·주가·차트·용어 사전 크롤링 API (rag_server/main.py에서 분리)
import urllib.parse
from typing import List

from fastapi import Body, HTTPException, Path
from fastapi.encoders import jsonable_encoder

import cache
import crawling
from crawling import NewsItemResponse, StockInfo, TermDefinitionOutput, TermInput
from myanalyst_common.web import create_app

app = create_app(title="MyAnalyst Market Data Service", service="market-data")

# 캐시 TTL(초). BE가 Redis에 캐시하던 값 그대로다(뉴스 5분, 시세 1분).
NEWS_TTL_SECONDS = 300
STOCK_TTL_SECONDS = 60

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
            
        cached = cache.get_json(f"news:{company_name}")
        if cached is not None:
            return cached

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
        
        cache.set_json(f"news:{company_name}", jsonable_encoder(response_items), NEWS_TTL_SECONDS)
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
        cached = cache.get_json(f"stocks:{company_name_query}")
        if cached is not None:
            return cached

        stock_data = crawling.get_stock_data_with_search(company_name_query)

        if not stock_data:
             raise HTTPException(status_code=404, detail=f"'{company_name_query}'에 대한 주식 정보를 구성할 수 없습니다.")
        cache.set_json(f"stocks:{company_name_query}", jsonable_encoder(stock_data), STOCK_TTL_SECONDS)
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
