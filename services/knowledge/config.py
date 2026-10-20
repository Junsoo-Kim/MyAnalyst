# config.py — knowledge-service / knowledge-ingest (검색 저장소를 소유하는 쪽의 설정)
import os
from dotenv import load_dotenv

load_dotenv()

# --- Embedding Model Settings ---
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "klue/bert-base")
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "768"))

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

# --- OpenSearch (BM25) Settings ---
# BM25는 서비스 프로세스 메모리가 아니라 OpenSearch에 인덱싱한다. 여러 인스턴스가
# 같은 인덱스를 공유하고, 색인은 knowledge-ingest가 별도로 수행한다.
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "myanalyst-chunks")

# --- Kafka (색인 완료 알림, 선택) ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
KAFKA_TOPIC_REPLICAS = int(os.getenv("KAFKA_TOPIC_REPLICAS", "1"))
KNOWLEDGE_INDEXED_TOPIC = "knowledge.indexed"

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
