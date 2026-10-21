"""검색 비교 평가용 데이터셋을 만든다(호스트에서 실행, requests·beautifulsoup4 필요).

  python services/knowledge/evals/build_retrieval_dataset.py --articles 20

1. ingest_sources/셀트리온_news_links_1.txt의 링크를 앞에서부터 받아 본문을 뽑는다. 본문 추출은 매체마다 다른
   구조를 일반 규칙(직계 텍스트가 가장 긴 블록)으로 처리하고, 품질 기준(길이, 한글 비율, 스크립트 흔적)을
   통과한 기사만 쓴다. --articles개가 모이면 멈춘다.
2. 기사 원문은 저작권이 있어 저장소에 넣지 않는다: evals/data/corpus.local.jsonl(.gitignore)에만 쓴다.
3. 저장소에 남기는 것은 기사 목록(articles.jsonl: url, 제목)과 질의(queries.jsonl: 질의 문자열, 정답 문장의
   SHA-1)뿐이다. 같은 링크를 다시 받으면 corpus를 재현할 수 있고, 기사가 바뀌었으면 평가가 그 질의를 건너뛴다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieval_dataset as ds  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
LINKS = HERE.parent / "ingest_sources" / "셀트리온_news_links_1.txt"
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", type=int, default=20)
    parser.add_argument("--per-article", type=int, default=2)
    args = parser.parse_args()

    links = [line.strip() for line in LINKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    DATA.mkdir(exist_ok=True)
    articles, corpus, queries = [], [], []
    seen_bodies = set()
    used_queries = set()
    tried = 0
    for url in links:
        if len(articles) >= args.articles:
            break
        tried += 1
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
            response.encoding = response.apparent_encoding
            if response.status_code != 200:
                continue
            body, title = extract_body(response.text), extract_title(response.text)
        except requests.RequestException:
            continue
        if not good_enough(body) or ds.sha1(body) in seen_bodies:
            continue
        sentences = ds.pick_query_sentences(body, args.per_article)
        if not sentences:
            continue
        seen_bodies.add(ds.sha1(body))
        article_id = f"a{len(articles):03d}"
        articles.append({"id": article_id, "url": url, "title": title})
        corpus.append({"id": article_id, "url": url, "title": title, "body": body})
        for n, sentence in enumerate(sentences):
            # 같은 보도자료를 여러 매체가 실으면 같은 질의가 반복된다. 한 번만 쓴다.
            if ds.keyword_query(sentence) in used_queries:
                continue
            used_queries.add(ds.keyword_query(sentence))
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
    print(f"tried {tried} links -> {len(articles)} articles, {len(queries)} queries "
          f"({sum(len(ds.chunk_article(c['body'])) for c in corpus)} chunks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
