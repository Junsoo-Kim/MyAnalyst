"""검색 비교 평가(retrieval_comparison_eval)의 데이터 규칙. 데이터를 만드는 쪽(build_retrieval_dataset, 호스트)과
평가하는 쪽(컨테이너)이 같은 문장 분리·청크·질의 규칙을 쓰도록 한 곳에 둔다. torch 등 무거운 의존은 없다.

질의는 사람이 고르지 않고 기사 본문 문장에서 규칙으로 만든다.
  - verbatim: 문장의 어절을 그대로 앞에서부터 N개 ("셀트리온은 올해 1분기 매출이 ...")
  - keyword : 같은 어절에서 끝의 조사를 떼고 서술어를 뺀 명사 위주 N개 ("셀트리온 올해 1분기 매출 ...")
keyword는 보고서 생성 파이프라인이 LLM으로 만든 검색 키워드(조사 없는 명사 나열)와 같은 모양이다.
정답은 그 문장이 들어 있는 청크 하나다(known-item 검색).
"""
import hashlib
import re
from typing import Dict, List, Optional

CHUNK_TARGET_LEN = 350
QUERY_TERMS = 5
MIN_SENTENCE_LEN = 40

# 길이가 긴 것부터 비교한다. 어절 끝에서 하나만 떼고, 남는 부분이 2글자 이상일 때만 뗀다
# ("평가"의 "가", "제도"의 "도"처럼 명사의 일부인 경우를 피하기 위해서).
PARTICLES = sorted([
    "에서는", "으로는", "에게는", "이라는", "에서도", "으로도", "까지는",
    "에서", "으로", "에게", "한테", "까지", "부터", "보다", "처럼", "라는", "이라", "에는", "와는", "과는",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
], key=len, reverse=True)

# 서술어·연결 어미로 끝나는 어절은 keyword 질의에서 뺀다(명사 위주로 남기기 위해).
VERBAL_ENDINGS = ("다", "고", "며", "면", "서", "지만", "는데", "했다", "된", "한", "할", "하는", "있는", "없는", "인", "될", "하며")
STOPWORDS = {"이번", "지난", "올해", "또한", "그리고", "이에", "이날", "현재", "관련", "통해", "대해", "위해", "따라", "등", "것", "수", "중"}

# 문장부호 뒤에서만 자른다. "다" 뒤에서 자르면 "보다", "만큼이다" 같은 어절 중간에서 문장이 끊긴다.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_EOJEOL = re.compile(r"[^\s\"'“”‘’()\[\]<>《》「」]+")


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def chunk_article(text: str, target_len: int = CHUNK_TARGET_LEN) -> List[str]:
    """문장 단위로 붙여 target_len 근처에서 자른다. 문장은 쪼개지 않으므로 정답 문장은 한 청크에만 들어간다."""
    chunks, current = [], ""
    for sentence in split_sentences(text):
        if current and len(current) + len(sentence) > target_len:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


def eojeols(sentence: str) -> List[str]:
    return [w.strip(".,·…:;!?") for w in _EOJEOL.findall(sentence) if w.strip(".,·…:;!?")]


def strip_particle(word: str) -> str:
    for particle in PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[: -len(particle)]
    return word


def verbatim_query(sentence: str, n: int = QUERY_TERMS) -> str:
    return " ".join(eojeols(sentence)[:n])


def keyword_terms(sentence: str) -> List[str]:
    terms = []
    for word in eojeols(sentence):
        if word.endswith(VERBAL_ENDINGS) and strip_particle(word) == word:
            continue
        term = strip_particle(word)
        if len(term) < 2 or term in STOPWORDS or not re.search(r"[가-힣A-Za-z0-9]", term):
            continue
        terms.append(term)
    return terms


def keyword_query(sentence: str, n: int = QUERY_TERMS) -> str:
    return " ".join(keyword_terms(sentence)[:n])


def pick_query_sentences(text: str, per_article: int = 2) -> List[str]:
    """첫 문장(기자명·매체 표기가 섞이는 리드)은 건너뛰고, 길이가 충분하고 조사가 붙은 어절이 2개 이상이며
    keyword 질의 단어가 QUERY_TERMS개 이상 나오는 문장 중 앞쪽 1개와 가운데 1개를 고른다."""
    candidates = []
    for sentence in split_sentences(text)[1:]:
        if len(sentence) < MIN_SENTENCE_LEN:
            continue
        words = eojeols(sentence)
        with_particle = sum(1 for w in words if strip_particle(w) != w)
        if with_particle >= 2 and len(keyword_terms(sentence)) >= QUERY_TERMS:
            candidates.append(sentence)
    if not candidates:
        return []
    picked = [candidates[0]]
    if per_article > 1 and len(candidates) > 2:
        picked.append(candidates[len(candidates) // 2])
    return picked[:per_article]


def relevant_chunk_index(text: str, sentence_sha1: str) -> Optional[int]:
    """정답 문장(해시)이 들어 있는 청크 번호. 기사가 바뀌어 문장을 못 찾으면 None."""
    sentence = next((s for s in split_sentences(text) if sha1(s) == sentence_sha1), None)
    if sentence is None:
        return None
    for index, chunk in enumerate(chunk_article(text)):
        if sentence in chunk:
            return index
    return None


def relevant_chunk_keys(corpus: Dict[str, dict], article_id: str, sentence_sha1: str) -> List[str]:
    """정답 청크 키("<article_id>:<chunk>") 목록. 같은 기사를 여러 매체가 실어 똑같은 문장이 다른 기사에도 있으면
    그 청크도 정답으로 센다(한 매체의 청크만 정답으로 두면 같은 내용을 찾아도 오답이 된다).
    원래 기사에서 문장을 못 찾으면(기사가 바뀜) 빈 목록."""
    if article_id not in corpus:
        return []
    target = next((s for s in split_sentences(corpus[article_id]["body"]) if sha1(s) == sentence_sha1), None)
    if target is None:
        return []
    target_words = set(eojeols(target))
    keys = []
    for other_id, article in corpus.items():
        for index, chunk in enumerate(chunk_article(article["body"])):
            # 같은 문장이거나, 매체마다 앞뒤 몇 어절만 다른 거의 같은 문장(어절 집합 Jaccard 0.8 이상)이면 정답이다.
            for sentence in split_sentences(chunk):
                words = set(eojeols(sentence))
                if sentence == target or (words and len(words & target_words) / len(words | target_words) >= 0.8):
                    keys.append(f"{other_id}:{index}")
                    break
    return sorted(set(keys))


def content_overlap(query: str, sentence: str) -> float:
    """질의 단어 중 원문 문장에 (조사를 떼고) 그대로 나오는 비율. 바꿔 쓴 질의가 원문 단어를 얼마나 피했는지 본다."""
    terms = [t for t in (strip_particle(w) for w in eojeols(query)) if len(t) >= 2]
    if not terms:
        return 0.0
    return sum(1 for t in terms if t in sentence) / len(terms)


def query_has_number(query: Dict[str, str]) -> bool:
    return bool(re.search(r"\d", query["keyword"]))
