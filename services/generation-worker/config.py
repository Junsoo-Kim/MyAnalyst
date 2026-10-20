# config.py — generation-worker 설정
import os
from dotenv import load_dotenv

load_dotenv()

# --- OpenAI Settings ---
# API 키·엔드포인트는 myanalyst_common.llm이 OPENAI_API_KEY / OPENAI_BASE_URL에서 읽는다.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# LLM 모델 설정도 환경 변수에서 불러옵니다
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")  # 기본값 설정
KEYWORD_LLM_MODEL = os.getenv("KEYWORD_LLM_MODEL", "gpt-4o-mini")
SUMMARY_LLM_MODEL = os.getenv("SUMMARY_LLM_MODEL", "gpt-4o-mini")

# --- Knowledge service (검색은 HTTP로 위임한다. 워커에는 임베딩 모델·Milvus 클라이언트가 없다) ---
KNOWLEDGE_SERVICE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8001")
KNOWLEDGE_TIMEOUT_SECONDS = float(os.getenv("KNOWLEDGE_TIMEOUT_SECONDS", "30"))
SEARCH_TOP_K = 20 # Number of results to retrieve overall

CORRECTIVE_RAG_ENABLED = os.getenv("CORRECTIVE_RAG_ENABLED", "true").lower() == "true"
GRADER_LLM_MODEL = os.getenv("GRADER_LLM_MODEL", "gpt-4o-mini")
MAX_GROUNDING_RETRIES = int(os.getenv("MAX_GROUNDING_RETRIES", "2"))

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "generation-worker")
KAFKA_TOPIC_PARTITIONS = int(os.getenv("KAFKA_TOPIC_PARTITIONS", "3"))
KAFKA_TOPIC_REPLICAS = int(os.getenv("KAFKA_TOPIC_REPLICAS", "1"))
# 한 메시지 처리(보고서 생성)는 수 분이 걸린다. 워커는 처리 중에도 poll을 계속하므로(pause/resume)
# 이 값은 "보고서 하나에 걸리는 시간"이 아니라 "poll 루프가 멈출 수 있는 최대 시간"이면 충분하다.
KAFKA_MAX_POLL_INTERVAL_MS = int(os.getenv("KAFKA_MAX_POLL_INTERVAL_MS", "300000"))
KAFKA_SESSION_TIMEOUT_MS = int(os.getenv("KAFKA_SESSION_TIMEOUT_MS", "45000"))

METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))

# --- Report Structure ---
REPORT_SECTIONS = {
    "2": "2024년 4분기 실적 분석",
    "3": "주요 사업 및 제품 동향",
    "4": "시장 환경 및 전략 방향",
    "5": "향후 전망 (공식 발표 기반)",
    "6": "기타 참고사항",
    "1": "보고서 요약 (Executive Summary)" # Summary is section 1, generated last
}

# Define the order in which sections 2-6 are generated
SECTION_GENERATION_ORDER = ["2", "3", "4", "5", "6"]
SUMMARY_SECTION_KEY = "1"

if not OPENAI_API_KEY:
    print("오류: OPENAI_API_KEY 환경 변수를 설정해주세요.")
