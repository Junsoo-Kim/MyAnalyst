"""검색 비교 평가용 데이터셋을 만든다(호스트에서 실행, requests·beautifulsoup4 필요).

  python services/knowledge/evals/build_retrieval_dataset.py --articles 160 --max-queries 300 --distractors 400

1. ingest_sources/셀트리온_news_links_{1,2,3}.txt의 링크를 순서대로 받아 본문을 뽑는다. 본문 추출은 매체마다 다른
   구조를 일반 규칙(직계 텍스트가 가장 긴 블록)으로 처리하고, 품질 기준(길이, 한글 비율, 스크립트 흔적)을
   통과한 기사만 쓴다. 앞의 --articles개는 질의를 만드는 기사, 그다음 --distractors개는
   검색 대상에만 들어가는 방해 기사다(정답과 비슷한 셀트리온 기사가 많아야 검색이 실제처럼 어려워진다).
2. 기사 원문은 저작권이 있어 저장소에 넣지 않는다: evals/data/corpus.local.jsonl(.gitignore)에만 쓴다.
3. 저장소에 남기는 것은 기사 목록(articles.jsonl: url, 제목)과 질의(queries.jsonl: 질의 문자열, 정답 문장의
   SHA-1)뿐이다. 같은 링크를 다시 받으면 corpus를 재현할 수 있고, 기사가 바뀌었으면 평가가 그 질의를 건너뛴다.
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieval_dataset as ds  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
LINK_FILES = [HERE.parent / "ingest_sources" / f"셀트리온_news_links_{n}.txt" for n in (1, 2, 3)]
USER_AGENT = "Mozilla/5.0 (MyAnalyst retrieval evaluation)"
DROP_TAGS = ["script", "style", "noscript", "header", "footer", "nav", "aside", "figure", "figcaption",
             "table", "form", "iframe", "button"]


def extract_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP_TAGS):
        tag.decompose()
    best = ""
    for element in soup.find_all(["article", "div", "section"]):
        parts = []
        for child in element.children:
            if isinstance(child, NavigableString):
                parts.append(str(child).strip())
            elif child.name in ("p", "br", "span", "b", "strong"):
                parts.append(child.get_text(" ", strip=True))
        text = " ".join(p for p in parts if p)
        if len(text) > len(best):
            best = text
    return clean_body(best)


# 일부 매체는 본문 중간에 광고 자리 표시 문자열을 넣는다("PC 기사뷰 3문단 하단 (20260313)// AD Manager | AD177... //").
_AD_NOISE = [re.compile(r"PC 기사\S*(?: \S+){0,3} ?\(\d{8}\)"), re.compile(r"AD Manager \| AD\d+"), re.compile(r"(?://\s*)+")]


def clean_body(text: str) -> str:
    for pattern in _AD_NOISE:
        text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    return soup.title.get_text(strip=True) if soup.title else ""


def good_enough(body: str) -> bool:
    if len(body) < 400 or "<script" in body or "function(" in body:
        return False
    hangul = len(re.findall(r"[가-힣]", body))
    return hangul / max(1, len(body)) > 0.4


def fetch(url: str):
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
        response.encoding = response.apparent_encoding
        if response.status_code != 200:
            return None
        return extract_body(response.text), extract_title(response.text)
    except requests.RequestException:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", type=int, default=20, help="질의를 만드는 기사 수")
    parser.add_argument("--max-queries", type=int, default=0, help="정답 문장 수 상한 (0이면 제한 없음)")
    parser.add_argument("--distractors", type=int, default=0, help="질의 없이 검색 대상에만 넣는 기사 수")
    parser.add_argument("--per-article", type=int, default=2)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    # 링크 파일 순서대로(파일 1 → 2 → 3) 중복 없이. 앞에서부터 질의 기사, 그다음 방해 기사로 쓴다.
    links = list(dict.fromkeys(
        line.strip() for path in LINK_FILES for line in path.read_text(encoding="utf-8").splitlines() if line.strip()))
    DATA.mkdir(exist_ok=True)
    articles, corpus, queries = [], [], []
    seen_bodies, used_queries = set(), []
    query_articles = 0
    tried = 0
    batch = args.workers * 4
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(links), batch):
            if query_articles >= args.articles and len(articles) - query_articles >= args.distractors:
                break
            urls = links[offset:offset + batch]
            for url, fetched in zip(urls, pool.map(fetch, urls)):  # 순서를 유지해 결과가 재현되게 한다
                tried += 1
                if fetched is None:
                    continue
                body, title = fetched
                if not good_enough(body) or ds.sha1(body) in seen_bodies:
                    continue
                wants_queries = query_articles < args.articles
                sentences = ds.pick_query_sentences(body, args.per_article) if wants_queries else []
                if wants_queries and not sentences:
                    continue
                if not wants_queries and len(articles) - query_articles >= args.distractors:
                    continue
                seen_bodies.add(ds.sha1(body))
                if wants_queries:
                    article_id, role = f"a{query_articles:03d}", "query"
                    query_articles += 1
                else:
                    article_id, role = f"d{len(articles) - query_articles:03d}", "distractor"
                articles.append({"id": article_id, "role": role, "url": url, "title": title})
                corpus.append({"id": article_id, "url": url, "title": title, "body": body})
                for n, sentence in enumerate(sentences):
                    if args.max_queries and len(queries) >= args.max_queries:
                        break
                    # 같은 보도자료를 여러 매체가 실으면 거의 같은 문장이 반복된다. 이미 고른 문장의 거의 같은 문장이면
                    # 건너뛴다. 그대로 두면 사실상 같은 질의가 여러 개가 되어 통계가 실제보다 확실해 보인다.
                    if any(ds.near_duplicate(sentence, seen) for seen in used_queries):
                        continue
                    used_queries.append(sentence)
                    queries.append({
                        "id": f"{article_id}-q{n}",
                        "article_id": article_id,
                        "sentence_sha1": ds.sha1(sentence),
                        "verbatim": ds.verbatim_query(sentence),
                        "keyword": ds.keyword_query(sentence),
                    })

    def write(name, rows):
        with open(DATA / name, "w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    write("articles.jsonl", articles)
    write("queries.jsonl", queries)
    write("corpus.local.jsonl", corpus)
    print(f"tried {tried} links -> {query_articles} query articles + {len(articles) - query_articles} distractors, "
          f"{len(queries)} queries ({sum(len(ds.chunk_article(c['body'])) for c in corpus)} chunks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
