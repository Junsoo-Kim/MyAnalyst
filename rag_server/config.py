# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# --- OpenAI Settings ---
# API 키는 환경 변수에서 불러옵니다
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None

# LLM 모델 설정도 환경 변수에서 불러옵니다
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")  # 기본값 설정
KEYWORD_LLM_MODEL = os.getenv("KEYWORD_LLM_MODEL", "gpt-4o-mini")
SUMMARY_LLM_MODEL = os.getenv("SUMMARY_LLM_MODEL", "gpt-4o-mini")

# --- Embedding Model Settings ---
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "klue/bert-base")
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "768"))  # 문자열을 정수로 변환

# --- Milvus Settings ---
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
# List of collections to search
COLLECTION_NAMES = ["celltrion_embeddings", "news_embeddings"]

# --- Search Settings ---
SEARCH_TOP_K = 20 # Number of results to retrieve overall
# Adjust SEARCH_PARAMS based on the index type used in your Milvus collections
SEARCH_PARAMS = {
    "metric_type": "L2",
    # For IVF_FLAT index:
    "params": {"nprobe": 10},
    # For HNSW index:
    # "params": {"ef": 64}
}

HYBRID_SEARCH_ENABLED = os.getenv("HYBRID_SEARCH_ENABLED", "true").lower() == "true"
BM25_TOP_K = int(os.getenv("BM25_TOP_K", str(SEARCH_TOP_K)))
RRF_K = int(os.getenv("RRF_K", "60"))

CORRECTIVE_RAG_ENABLED = os.getenv("CORRECTIVE_RAG_ENABLED", "true").lower() == "true"
GRADER_LLM_MODEL = os.getenv("GRADER_LLM_MODEL", "gpt-4o-mini")
MAX_GROUNDING_RETRIES = int(os.getenv("MAX_GROUNDING_RETRIES", "2"))

# --- Field Mappings per Collection ---
# Define the name of the field containing the main text content for each collection
# Also define any additional metadata fields you want to include in the context
COLLECTION_FIELD_MAPPINGS = {
    "celltrion_embeddings": {
        "text_field": "text",
        "output_fields": ["text"] # Include other fields if needed
    },
    "news_embeddings": {
        "text_field": "chunk_text",
        "output_fields": [
            "chunk_text", "original_article_id", "chunk_seq_id",
            "title", "datetime", "summary", "url"
        ]
    }
    # Add mappings for other collections if needed
}

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


# Check if essential configurations are set
if not OPENAI_API_KEY or OPENAI_API_KEY == "YOUR_FALLBACK_API_KEY":
    print("오류: config.py에서 OPENAI_API_KEY를 설정하거나 환경 변수로 제공해주세요.")
    # Consider raising an exception or exiting if the key is mandatory
    # raise ValueError("OpenAI API Key is not configured.")