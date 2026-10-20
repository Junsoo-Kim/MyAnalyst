import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup

def scroll_down(driver, scroll_pause_time=2, max_scrolls=10):
    """페이지를 아래로 스크롤하여 더 많은 콘텐츠를 로드합니다."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0

    while scroll_count < max_scrolls:
        # 페이지 맨 아래로 스크롤
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        # 페이지 로드를 기다림
        time.sleep(scroll_pause_time)
        # 새 높이 계산하고 이전 높이와 비교
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print("더 이상 로드할 콘텐츠가 없습니다.")
            break
        last_height = new_height
        scroll_count += 1
        print(f"스크롤 {scroll_count}회 완료...")
    print(f"총 {scroll_count}회 스크롤했습니다.")

def crawl_naver_news(query):
    # Chrome WebDriver 설정
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # 브라우저 창을 띄우지 않음 (필요에 따라 주석 해제)
    options.add_argument("--start-maximized") # 브라우저 최대화
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36") # User-Agent 설정
    options.add_experimental_option("excludeSwitches", ["enable-automation"]) # 자동화 탐지 회피
    options.add_experimental_option('useAutomationExtension', False) # 자동화 확장 기능 사용 안함

    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

    # 네이버 뉴스 검색 URL (쿼리 파라미터 사용)
    # search_url = f"https://search.naver.com/search.naver?where=news&query={query}"
    # 2024년 기준 URL 구조가 다소 변경되었을 수 있으니, 실제 검색 결과 페이지 URL을 확인하세요.
    # 예시: https://search.naver.com/search.naver?sm=tab_hty.top&where=news&ssc=tab.news.all&query=검색어
    search_url = f"https://search.naver.com/search.naver?ssc=tab.news.all&query=%EC%85%80%ED%8A%B8%EB%A6%AC%EC%98%A8&sm=tab_opt&sort=1&photo=0&field=0&pd=3&ds=2023.02.19&de=2025.02.19&docid=&related=0&mynews=1&office_type=3&office_section_code=0&news_office_checked=&nso=so%3Add%2Cp%3Afrom20230219to20250219&is_sug_officeid=0&office_category=3&service_area="
    
    print(f"'{query}'에 대한 네이버 뉴스 검색을 시작합니다...")
    driver.get(search_url)
    time.sleep(2) # 페이지 초기 로드 대기

    # 무한 스크롤 실행 (예: 최대 5번 스크롤 또는 더 이상 콘텐츠가 없을 때까지)
    scroll_down(driver, scroll_pause_time=3, max_scrolls=1000) # 필요에 따라 scroll_pause_time과 max_scrolls 조정

    # 페이지 소스 가져오기
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')

    # 파일로 HTML 저장 (디버깅용)
    with open("naver_news_page.html", "w", encoding="utf-8") as f:
        f.write(page_source)
    print("naver_news_page.html 파일로 현재 페이지 DOM 구조를 저장했습니다.")

    # 다양한 네이버 뉴스 선택자 시도
    news_item_elements = []
    
    # 1. 먼저 일반적인 선택자 시도
    news_item_elements = soup.select("ul.list_news > div > div > div > div > div")
    print(f"list_news > li 선택자 결과: {len(news_item_elements)}개")
    
    # 2. fdr-root 선택자 시도
    if not news_item_elements:
        news_item_elements = soup.select("div#fdr-root ul > li")
        print(f"fdr-root 선택자 결과: {len(news_item_elements)}개")
    
    # 3. api_subject_bx 내의 뉴스 항목 찾기
    if not news_item_elements:
        news_item_elements = soup.select("div.api_subject_bx li.item")
        print(f"api_subject_bx li.item 선택자 결과: {len(news_item_elements)}개")
    
    # 4. 2024년 새로운 네이버 뉴스 검색 결과 형식
    if not news_item_elements:
        news_item_elements = soup.select("div.VHZYYmCzYQ_aA_TI9qoq > div > div > div.iYo99IP8GixD0iM_4cb8")
        print(f"VHZYYmCzYQ_aA_TI9qoq 선택자 결과: {len(news_item_elements)}개")
    
    # 5. 더 일반적인 선택자 시도
    if not news_item_elements:
        news_item_elements = soup.select("div.group_news ul > li")
        print(f"group_news 선택자 결과: {len(news_item_elements)}개")
    
    print(f"최종 선택된 뉴스 요소 수: {len(news_item_elements)}개")
    
    # 뉴스 요소가 없으면 빈 리스트 반환
    results = []
    if not news_item_elements:
        print("뉴스 아이템을 찾지 못했습니다. CSS 선택자를 확인해주세요.")
        driver.quit()
        return results

    rank_counter = 1
    for item_element in news_item_elements:
        print(f"=== 처리 중인 요소 {rank_counter} ===")
        
        title = None
        link = None
        summary = None
        press = None
        published_info = None
        
        # 제목과 링크 추출 (새로운 선택자 사용)
        title_info = item_element.select_one("a.news_tit")
        if title_info:
            title = title_info.get_text(strip=True)
            link = title_info.get("href")
            print(f"제목: {title[:30]}...")
        
        # 대체 방법: OgU1CD78f4cPaKGs1OeY 클래스 시도
        if not title or not link:
            title_info = item_element.select_one("a.OgU1CD78f4cPaKGs1OeY")
            if title_info:
                title = title_info.get_text(strip=True)
                link = title_info.get("href")
                print(f"OgU1CD78f4cPaKGs1OeY 클래스로 제목 찾음: {title[:30]}...")
        
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
        summary_tag = item_element.select_one("div.news_dsc, a.IaKmSOGPdofdPwPE6cyU, span.sds-comps-text-ellipsis-3")
        if summary_tag:
            summary = summary_tag.get_text(strip=True)
            print(f"요약: {summary[:30]}...")
        
        # 언론사 정보 추출
        press_tag = item_element.select_one("a.info.press, span.sds-comps-profile-info-title-text a, a.jTrMMxVViEpMe6SA4ef2")
        if press_tag:
            press = press_tag.get_text(strip=True)
            print(f"언론사: {press}")
        
        # 시간 정보 추출
        time_tag = item_element.select_one("span.info, span.sds-comps-text-type-body2.sds-comps-text-weight-sm:not(.sds-comps-profile-info-title-text)")
        if time_tag:
            published_info = time_tag.get_text(strip=True)
            print(f"발행 정보: {published_info}")
        
        # 필수 정보(제목과 링크)가 있는 경우에만 뉴스 항목 추가
        if title and link:
            print(f"뉴스 항목 {rank_counter} 추가: {title[:30]}...")
            
            results.append({
                'rank': rank_counter,
                'title': title,
                'link': link,
                'summary': summary,
                'press': press,
                'published_info': published_info,
            })
            rank_counter += 1

    # 드라이버 종료
    driver.quit()
    return results

if __name__ == "__main__":
    search_query = "셀트리온"  # 여기에 검색어를 입력하세요
    crawled_news = crawl_naver_news(search_query)
    print(f"\n총 {len(crawled_news)}개의 뉴스 기사를 수집했습니다.")
    
    # 수집된 뉴스 링크만 txt 파일로 저장
    if crawled_news:
        output_file = f"셀트리온_news_links.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            for news in crawled_news:
                if 'link' in news and news['link']:
                    f.write(f"{news['link']}\n")
        print(f"\n{len(crawled_news)}개의 뉴스 링크를 '{output_file}' 파일로 저장했습니다.")