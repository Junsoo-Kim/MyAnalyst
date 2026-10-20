import argparse
from crawling import crawl_naver_news_for_company

def save_links_to_file(company_name: str, limit: int = 20, output_file: str = None):
    """
    특정 회사에 대한 네이버 뉴스를 크롤링하고 링크만 텍스트 파일로 저장합니다.
    
    Args:
        company_name: 검색할 회사 이름
        limit: 가져올 뉴스 항목 최대 개수
        output_file: 저장할 파일명 (기본값: {company_name}_news_links.txt)
    """
    print(f"'{company_name}'에 대한 뉴스 링크를 수집합니다...")
    
    # 뉴스 크롤링
    news_items = crawl_naver_news_for_company(company_name, limit)
    
    # 출력 파일 이름 설정
    if not output_file:
        output_file = f"{company_name}_news_links.txt"
    
    # 링크만 추출하여 파일로 저장
    with open(output_file, "w", encoding="utf-8") as f:
        for news in news_items:
            f.write(f"{news.link}\n")
    
    print(f"총 {len(news_items)}개의 뉴스 링크를 '{output_file}' 파일로 저장했습니다.")
    return news_items

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 뉴스 링크 수집기")
    parser.add_argument("company", help="검색할 회사 이름")
    parser.add_argument("-n", "--limit", type=int, default=20, help="수집할 뉴스 최대 개수 (기본값: 20)")
    parser.add_argument("-o", "--output", help="저장할 파일 경로 (기본값: {회사명}_news_links.txt)")
    
    args = parser.parse_args()
    save_links_to_file(args.company, args.limit, args.output)
