from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from bs4 import BeautifulSoup
from typing import List
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional
import requests
import urllib.parse
from datetime import datetime
import io

# utils.py에서 가져오는 함수를 직접 구현
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

_NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}


def resolve_stock_code(company_name_query: str) -> str:
    search_url = "https://ac.stock.naver.com/ac"
    try:
        response = requests.get(
            search_url,
            params={"q": company_name_query, "target": "stock"},
            headers=_NAVER_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"네이버 증권 서버에서 종목 검색에 실패했습니다: {str(e)}")

    items = response.json().get("items", [])
    if not items:
        raise HTTPException(status_code=404, detail=f"'{company_name_query}'에 해당하는 종목을 네이버 증권에서 찾을 수 없습니다.")

    exact_match = next((item for item in items if item.get("name") == company_name_query), None)
    match = exact_match or items[0]
    stock_code = match.get("code")
    if not stock_code:
        raise HTTPException(status_code=404, detail="검색된 종목에서 종목 코드를 추출할 수 없습니다.")

    return stock_code

class NewsItem(BaseModel):
    rank: int # 순위
    title: str # 제목
    link: HttpUrl # 뉴스 링크 (Pydantic이 URL 형식 검증)
    summary: Optional[str] = None # 요약 (없을 수도 있음)
    press: Optional[str] = None # 언론사 (없을 수도 있음)
    published_info: Optional[str] = None # 발행 정보 (예: "1시간 전", "YTN", "2023.01.01.")

class NewsItemResponse(BaseModel):
    title: str # 제목
    link: HttpUrl # 뉴스 링크 (Pydantic이 URL 형식 검증)
    summary: Optional[str] = None # 요약 (없을 수도 있음)
    press: Optional[str] = None # 언론사 (없을 수도 있음)

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

# 요청 본문의 각 아이템에 대한 모델
class TermInput(BaseModel):
    term: str = Field(..., description="뜻을 검색할 단어")
    explanation: Optional[str] = Field(None, description="사용자 제공 설명 (API는 이 값을 사용하지 않음)")

# 응답 본문의 각 아이템에 대한 모델 (수정됨)
class TermDefinitionOutput(BaseModel):
    term: str = Field(..., description="검색한 단어")
    definitions: List[str] = Field(..., description="네이버 사전에서 크롤링한 뜻 목록")
    source_url: Optional[HttpUrl] = Field(None, description="뜻을 가져온 검색 결과 페이지 URL") # 추가된 필드

def crawl_naver_news_for_company(company_name: str, limit: int = 10) -> List[NewsItem]:
    """
    특정 회사에 대한 최신 네이버 뉴스를 크롤링합니다.
    """
    encoded_company_name = urllib.parse.quote(company_name) # 회사명을 URL 인코딩
    # sort=1은 '최신순' 정렬을 의미합니다.
    search_url = f"https://search.naver.com/search.naver?where=news&query={encoded_company_name}&sm=tab_opt&sort=1"
    
    print(f"크롤링 요청 URL: {search_url}")  # 디버깅을 위한 URL 출력

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
    news_list: List[NewsItem] = []

    try:
        # 타임아웃을 10초로 설정
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status() # HTTP 오류(4xx 또는 5xx) 발생 시 예외를 발생시킴
        
        # 응답 내용의 일부를 출력하여 디버깅 (너무 길지 않게 제한)
        print(f"응답 상태 코드: {response.status_code}")
        print(f"응답 내용 미리보기: {response.text[:300]}...")

        # response.text 내용을 html 파일로 저장
        with open("naver_news_response.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        
    except requests.exceptions.RequestException as e:
        print(f"URL 가져오기 오류: {e}")
        # API 엔드포인트 핸들러에서 처리하도록 예외를 다시 발생시킬 수 있습니다.
        raise HTTPException(status_code=503, detail=f"네이버에서 뉴스 정보를 가져올 수 없습니다: {str(e)}")

    soup = BeautifulSoup(response.text, "html.parser") # 응답받은 HTML 텍스트를 파싱
    
    # 2024년 네이버 뉴스 검색 결과의 구조에 맞게 선택자 지정
    # 네이버 뉴스 검색 결과는 ul.list_news 내에 여러 li 태그로 구성됨
    # news_item_elements = soup.select("ul.list_news > li")
    news_item_elements = soup.select("ul.list_news > div > div > div > div > div")
    print(f"list_news 선택자 결과: {len(news_item_elements)}개")
    print(news_item_elements)

    # 새로운 형식: 클래스명이 변경된 경우 대비
    if not news_item_elements:
        news_item_elements = soup.select("div#fdr-root ul > li")
        print(f"fdr-root 선택자 결과: {len(news_item_elements)}개")
    
    # 2024년 새로운 네이버 뉴스 검색 결과 형식
    if not news_item_elements:
        news_item_elements = soup.select("div.VHZYYmCzYQ_aA_TI9qoq > div > div > div.iYo99IP8GixD0iM_4cb8")
        print(f"VHZYYmCzYQ_aA_TI9qoq 선택자 결과: {len(news_item_elements)}개")
    
    # 더 일반적인 선택자 시도
    if not news_item_elements:
        news_item_elements = soup.select("div.group_news ul > li")
        print(f"group_news 선택자 결과: {len(news_item_elements)}개")

    print(f"최종 선택된 뉴스 요소 수: {len(news_item_elements)}")
    
    # 뉴스 요소가 없으면 빈 리스트 반환
    if not news_item_elements:
        return []

    rank_counter = 1
    for item_element in news_item_elements:
        if rank_counter > limit:  # 요청된 개수만큼만 가져오도록 제한
            break
        
        print(f"=== 처리 중인 요소 {rank_counter} ===")
        
        # 2024년 네이버 뉴스 검색 결과 구조에 맞게 선택자 수정
        title_tag = None
        link = None
        title = None
        
        # 제목과 링크 추출 (새로운 선택자 사용)
        title_info = item_element.select_one("a.OgU1CD78f4cPaKGs1OeY")
        if title_info:
            title = title_info.get_text(strip=True)
            link = title_info.get("href")
            print(f"제목: {title[:30]}...")
        
        # 대체 방법: 모든 a 태그 중 뉴스 제목과 링크가 있는 것 찾기
        if not title or not link:
            all_links = item_element.select("a")
            for a_tag in all_links:
                href = a_tag.get("href")
                text = a_tag.get_text(strip=True)
                if href and text and len(text) > 10:  # 뉴스 제목은 일반적으로 길다
                    title = text
                    link = href
                    print(f"대체 방법으로 제목 찾음: {title[:30]}...")
                    break
        
        # 요약 추출
        summary = None
        summary_tag = item_element.select_one("a.IaKmSOGPdofdPwPE6cyU, span.sds-comps-text-ellipsis-3")
        if summary_tag:
            summary = summary_tag.get_text(strip=True)
        
        # 언론사 정보 추출
        press = None
        press_tag = item_element.select_one("span.sds-comps-profile-info-title-text a, a.jTrMMxVViEpMe6SA4ef2")
        if press_tag:
            press = press_tag.get_text(strip=True)
        
        # 시간 정보 추출
        published_info = None
        time_tag = item_element.select_one("span.sds-comps-text-type-body2.sds-comps-text-weight-sm:not(.sds-comps-profile-info-title-text)")
        if time_tag:
            published_info = time_tag.get_text(strip=True)
            
        # 필수 정보(제목과 링크)가 있는 경우에만 뉴스 항목 추가
        if title and link:
            print(f"뉴스 항목 {rank_counter} 추가: {title[:30]}...")
            
            news_list.append(
                NewsItem(
                    rank=rank_counter,
                    title=title,
                    link=link,
                    summary=summary,
                    press=press,
                    published_info=published_info,
                )
            )
            rank_counter += 1
    
    return news_list


def get_stock_data_with_search(company_name_query: str) -> Optional[StockInfo]:
    stock_code = resolve_stock_code(company_name_query)

    item_main_url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
    try:
        item_response = requests.get(item_main_url, headers=_NAVER_HEADERS, timeout=10)
        item_response.raise_for_status()
        html_content_to_parse = item_response.text
    except requests.exceptions.RequestException as e:
        print(f"종목 상세 정보 페이지 로드 실패 ({stock_code}): {e}")
        raise HTTPException(status_code=503, detail=f"네이버 증권 서버에서 {stock_code}의 상세 정보 로드에 실패했습니다: {str(e)}")

    return crawl_naver_finance_from_html(html_content_to_parse, stock_code, company_name_query, item_main_url)

def crawl_naver_finance_from_html(html_content: str, stock_code_from_url: str, company_name_from_search: str, item_main_url: str = None) -> StockInfo:
    item_soup = BeautifulSoup(html_content, "lxml")

    # --- 정보 추출 시작 (제공된 HTML 기준 선택자) ---
    info = StockInfo(
        retrieved_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
        company_name=company_name_from_search, # 우선 검색어로 초기화
        stock_code=stock_code_from_url,
        item_main_url=item_main_url
    )

    # 데이터 기준 시각
    time_tag = item_soup.select_one("div.description span#time em.date")
    if time_tag:
        info.data_timestamp_info = get_safe_text(time_tag)

    # 회사명 (페이지에서 가져오기)
    company_name_tag = item_soup.select_one("div.wrap_company h2 > a")
    if company_name_tag:
        info.company_name = get_safe_text(company_name_tag)
    
    # 종목 코드 (페이지에서 확인 - URL과 동일해야 함)
    code_tag = item_soup.select_one("div.description span.code")
    if code_tag and get_safe_text(code_tag) != info.stock_code:
        # URL의 코드와 페이지의 코드가 다를 경우 경고 또는 로직 수정 필요
        print(f"Warning: URL stock code {info.stock_code} and page stock code {get_safe_text(code_tag)} differ.")

    # 시장 구분 (코스피/코스닥)
    market_img = item_soup.select_one("div.description img.kospi, div.description img.kosdaq")
    if market_img:
        info.market_type = market_img.get("alt", "").strip()

    # KRX 시장의 현재가, 전일비, 등락률 영역 (ID 'rate_info_krx' 내부)
    # 실제 HTML 파일에는 KRX와 NXT 정보가 모두 있을 수 있습니다. KRX를 우선으로 합니다.
    krx_rate_info_area = item_soup.select_one("div#rate_info_krx")
    if not krx_rate_info_area : # NXT만 있거나 다른 구조일 경우 대비
        krx_rate_info_area = item_soup.select_one("div.rate_info") # 일반적인 rate_info 선택

    if krx_rate_info_area:
        # 현재가
        current_price_em = krx_rate_info_area.select_one("p.no_today em")
        if current_price_em:
            # em 태그 내부의 span들이 숫자를 구성 (예: <span class="no1">1</span><span class="no5">5</span>...)
            price_spans = current_price_em.find_all(lambda tag: tag.name == 'span' and (tag.has_attr('class') and any(cls.startswith('no') for cls in tag['class'])))
            if price_spans:
                info.current_price = clean_price_data("".join(s.get_text() for s in price_spans))
            else: # span 구성이 아닌 직접 em text인 경우
                info.current_price = clean_price_data(get_safe_text(current_price_em))


        # 전일비, 등락률
        exday_info = krx_rate_info_area.select_one("p.no_exday")
        if exday_info:
            ems_in_exday = exday_info.select("em") # 보통 2개의 em (변동액, 변동률)
            if len(ems_in_exday) >= 1:
                price_change_em = ems_in_exday[0]
                price_change_text_parts = []
                sign = ""
                if "up" in price_change_em.get("class", []): sign = "+"
                elif "down" in price_change_em.get("class", []): sign = "-"
                
                for child in price_change_em.children:
                    if child.name == 'span' and any(cls.startswith('no') for cls in child.get('class', [])):
                        price_change_text_parts.append(child.get_text())
                    elif child.name == 'span' and 'shim' in child.get('class', []): # 쉼표
                         price_change_text_parts.append(child.get_text())
                
                if price_change_text_parts:
                    info.price_change = sign + "".join(price_change_text_parts)
                elif get_safe_text(price_change_em.select_one("span.blind")): # blind 안에 숫자만 있을 경우 (예: 보합)
                    blind_text = get_safe_text(price_change_em.select_one("span.blind"))
                    if blind_text and blind_text.replace(',','').isdigit(): # 보합은 '0'이 아닐 수 있음.
                         info.price_change = sign + clean_price_data(blind_text)


            if len(ems_in_exday) >= 2:
                change_rate_em = ems_in_exday[1]
                rate_text_parts = []
                rate_sign = ""
                if "up" in change_rate_em.get("class", []): rate_sign = "+"
                elif "down" in change_rate_em.get("class", []): rate_sign = "-"

                for child in change_rate_em.children:
                    if child.name == 'span' and (any(cls.startswith('no') for cls in child.get('class', [])) or 'jum' in child.get('class', [])):
                        rate_text_parts.append(child.get_text())
                
                if rate_text_parts:
                    info.change_rate = rate_sign + "".join(rate_text_parts) + get_safe_text(change_rate_em.select_one("span.per"),"")
                elif get_safe_text(change_rate_em.select_one("span.blind")): # blind 안에 숫자만 있을 경우
                     blind_text = get_safe_text(change_rate_em.select_one("span.blind"))
                     if blind_text:
                        info.change_rate = rate_sign + clean_price_data(blind_text) + get_safe_text(change_rate_em.select_one("span.per"),"")


    # 주요 시세 테이블 (전일, 시가, 고가, 저가, 상한/하한, 거래량, 거래대금)
    # KRX 기준: div#rate_info_krx table.no_info
    main_sise_table = item_soup.select_one("div#rate_info_krx table.no_info")
    if not main_sise_table: # Fallback
        main_sise_table = item_soup.select_one("div.rate_info table.no_info")

    if main_sise_table:
        rows = main_sise_table.select("tr")
        if len(rows) == 2:
            # 첫 번째 행: 전일, 고가, 상한가, 거래량
            cols_row1 = rows[0].select("td")
            if len(cols_row1) == 3:
                # 전일
                yesterday_em = cols_row1[0].select_one("em")
                info.yesterday_close = clean_price_data(get_safe_text(yesterday_em))
                # 고가, 상한가
                high_price_em = cols_row1[1].select_one("em") # 첫번째 em이 고가
                info.high_price = clean_price_data(get_safe_text(high_price_em))
                upper_limit_em = cols_row1[1].select_one("em.no_cha") # 상한가
                info.upper_limit_price = clean_price_data(get_safe_text(upper_limit_em))
                # 거래량
                volume_em = cols_row1[2].select_one("em")
                info.volume = clean_price_data(get_safe_text(volume_em))

            # 두 번째 행: 시가, 저가, 하한가, 거래대금
            cols_row2 = rows[1].select("td")
            if len(cols_row2) == 3:
                # 시가
                open_price_em = cols_row2[0].select_one("em")
                info.open_price = clean_price_data(get_safe_text(open_price_em))
                # 저가, 하한가
                low_price_em = cols_row2[1].select_one("em") # 첫번째 em이 저가
                info.low_price = clean_price_data(get_safe_text(low_price_em))
                lower_limit_em = cols_row2[1].select_one("em.no_cha") # 하한가
                info.lower_limit_price = clean_price_data(get_safe_text(lower_limit_em))
                # 거래대금
                volume_value_em = cols_row2[2].select_one("em")
                volume_value_unit = get_safe_text(cols_row2[2].select_one("span.sptxt.sp_txt11"), "") # "백만"
                info.volume_value = clean_price_data(get_safe_text(volume_value_em)) + volume_value_unit
                
    # --- 우측 사이드바 정보 (div#aside div.aside_invest_info div#tab_con1) ---
    aside_tab_con1 = item_soup.select_one("div#aside div#tab_con1")
    if aside_tab_con1:
        # 시가총액, 순위, 상장주식수
        first_table = aside_tab_con1.select_one("div.first table")
        if first_table:
            market_cap_em = first_table.select_one("tr td em#_market_sum")
            if market_cap_em:
                market_cap_text = get_safe_text(market_cap_em)
                market_cap_unit = get_safe_text(market_cap_em.find_next_sibling(string=True), "").strip() # "억원"
                info.market_cap = f"{market_cap_text}{market_cap_unit}"
            
            for row in first_table.select("tr"):
                th_text = get_safe_text(row.select_one("th a.link_site, th"))
                td_text = get_safe_text(row.select_one("td"))
                if th_text and "시가총액순위" in th_text:
                    info.market_cap_rank = td_text
                elif th_text and "상장주식수" in th_text:
                    info.shares_outstanding = clean_price_data(get_safe_text(row.select_one("td em")))
        
        # 외국인 소진율
        gray_table = aside_tab_con1.select_one("div.gray table")
        if gray_table:
            foreign_ratio_row = gray_table.select_one("tr:has(strong:contains('외국인소진율'))")
            if foreign_ratio_row:
                info.foreign_ownership_ratio = get_safe_text(foreign_ratio_row.select_one("td em"))

        # 52주 최고/최저
        rwidth_table = aside_tab_con1.select_one("table.rwidth") # 투자의견, 52주
        if rwidth_table:
            fifty_two_week_row = rwidth_table.select_one("tr:has(th:contains('52주최고'))")
            if fifty_two_week_row:
                td_text = get_safe_text(fifty_two_week_row.select_one("td"))
                if td_text and "l" in td_text:
                    parts = td_text.split("l")
                    info.fifty_two_week_high = clean_price_data(parts[0].strip())
                    info.fifty_two_week_low = clean_price_data(parts[1].strip())

        # PER, EPS, PBR, BPS, 배당수익률
        per_table = aside_tab_con1.select_one("table.per_table")
        if per_table:
            for row in per_table.select("tr"):
                th_text = get_safe_text(row.select_one("th"))
                td_ems = row.select("td em") # 보통 em 태그 안에 값이 있음
                td_text_full = get_safe_text(row.select_one("td")) # 날짜 정보 등 포함

                if th_text and "PER" in th_text and "EPS" in th_text and "추정PER" not in th_text :
                    if len(td_ems) >= 2:
                        info.per_info = get_safe_text(td_ems[0]) + get_safe_text(td_ems[0].find_next_sibling(string=True), "").strip() # "배"
                        info.eps_info = get_safe_text(td_ems[1]) + get_safe_text(td_ems[1].find_next_sibling(string=True), "").strip() # "원"
                        date_info = get_safe_text(row.select_one("th span.date"))
                        if date_info :
                             info.per_info += f" ({date_info})"
                             info.eps_info += f" ({date_info})"
                elif th_text and "추정PER" in th_text:
                    if len(td_ems) >= 2:
                        info.estimated_per_info = get_safe_text(td_ems[0]) + get_safe_text(td_ems[0].find_next_sibling(string=True), "").strip()
                        info.estimated_eps_info = get_safe_text(td_ems[1]) + get_safe_text(td_ems[1].find_next_sibling(string=True), "").strip()
                elif th_text and "PBR" in th_text and "BPS" in th_text:
                     if len(td_ems) >= 2:
                        info.pbr_info = get_safe_text(td_ems[0]) + get_safe_text(td_ems[0].find_next_sibling(string=True), "").strip()
                        info.bps_info = get_safe_text(td_ems[1]) + get_safe_text(td_ems[1].find_next_sibling(string=True), "").strip()
                        date_info = get_safe_text(row.select_one("th span.date"))
                        if date_info :
                             info.pbr_info += f" ({date_info})"
                             info.bps_info += f" ({date_info})"
                elif th_text and "배당수익률" in th_text:
                    if td_ems:
                        info.dividend_yield_info = get_safe_text(td_ems[0])
                        date_info = get_safe_text(row.select_one("th span.date, th > span:not([class])")) # 날짜 정보
                        if date_info : info.dividend_yield_info += f" ({date_info})"


        # 동일업종 PER
        industry_per_table = aside_tab_con1.select_one("div.gray table:has(a:contains('동일업종 PER'))") # 마지막 gray 테이블
        if industry_per_table:
             industry_per_row = industry_per_table.select_one("tr:has(a:contains('동일업종 PER'))")
             if industry_per_row:
                 info.industry_per_info = get_safe_text(industry_per_row.select_one("td em"))
                 
    return info

async def get_chart_image_data(company_name_query: str) -> StreamingResponse:
    stock_code = resolve_stock_code(company_name_query)

    # 종목 상세 페이지 HTML 가져오기
    item_main_url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
    try:
        item_response = requests.get(item_main_url, headers=_NAVER_HEADERS, timeout=10)
        item_response.raise_for_status()
        item_soup = BeautifulSoup(item_response.text, "lxml")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"종목 상세 페이지 로드 실패: {str(e)}")

    # 3. 차트 이미지 URL 추출
    chart_img_tag = item_soup.select_one("img#img_chart_area")
    if not chart_img_tag or not chart_img_tag.get("src"):
        raise HTTPException(status_code=404, detail="차트 이미지 정보를 찾을 수 없습니다.")

    chart_image_url = chart_img_tag["src"]

    # 4. 이미지 데이터 가져오기
    try:
        image_response = requests.get(chart_image_url, headers=_NAVER_HEADERS, stream=True, timeout=10)
        image_response.raise_for_status()
        
        # 이미지 내용을 메모리에 로드
        image_bytes = io.BytesIO(image_response.content)
        
        # StreamingResponse로 이미지 반환
        return StreamingResponse(image_bytes, media_type="image/png")
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"차트 이미지 다운로드 실패: {str(e)}")

def crawl_naver_dictionary_for_term(term: str) -> TermDefinitionOutput:
    """
    주어진 단어의 뜻을 네이버 사전 (learn.dict.naver.com)에서 크롤링하고,
    검색 결과 페이지 URL을 포함하여 반환합니다.
    """
    encoded_term = urllib.parse.quote(term)
    search_url = f"https://learn.dict.naver.com/search.nhn?query={encoded_term}"
    
    definitions: List[str] = []
    final_source_url: Optional[HttpUrl] = search_url # 기본적으로 검색 URL을 사용

    try:
        response = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
}, timeout=10)
        response.raise_for_status()
        # 실제 요청 후 최종 URL (리다이렉션이 있었을 경우)
        # final_source_url = response.url # learn.dict.naver.com은 리다이렉션이 거의 없어 search_url과 동일할 가능성 높음
    except requests.exceptions.RequestException as e:
        print(f"'{term}'에 대한 사전 페이지 요청 실패: {e}")
        return TermDefinitionOutput(
            term=term, 
            definitions=[f"사전 페이지 요청 오류: {str(e)}"], 
            source_url=search_url # 오류 발생 시에도 시도했던 URL 반환
        )

    soup = BeautifulSoup(response.text, "lxml")

    # 1. <div class="article"> 내부의 뜻을 우선 검색 (주로 학술 용어 등)
    article_div = soup.select_one("div.article")
    if article_div:
        mean_p = article_div.select_one("p.mean")
        if mean_p and mean_p.get_text(strip=True):
            definitions.append(mean_p.get_text(strip=True))
            # 이 경우 source_url은 search_url 그대로 사용

    # 2. <div class="article">에 뜻이 없다면, 각 사전 섹션 검색
    if not definitions:
        dictionary_sections = soup.select("div.section[id]")
        for section in dictionary_sections:
            meanings_in_section = section.select("ul.lst > li > p.mean")
            if meanings_in_section:
                for mean_p in meanings_in_section:
                    definition_text = mean_p.get_text(strip=True)
                    if definition_text:
                        definitions.append(definition_text)
                if definitions: # 첫 번째 섹션에서 뜻을 찾으면 중단
                    # 이 경우에도 source_url은 search_url 그대로 사용
                    break 
    
    if not definitions:
        definitions.append("네이버 사전에서 뜻을 찾을 수 없습니다.")

    return TermDefinitionOutput(term=term, definitions=definitions, source_url=final_source_url)
