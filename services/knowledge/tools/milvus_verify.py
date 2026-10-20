"""
Milvus 데이터 검증 도구

이 도구는 Milvus 컬렉션의 데이터를 검증하고, 실제 텍스트 내용이 올바르게 저장되어 있는지 확인합니다.
또한 검색 기능을 테스트하여 RAG 시스템이 올바르게 작동하는지 검증합니다.
"""

import os
import sys
import json
from typing import List, Dict, Any, Optional
import numpy as np
from pymilvus import connections, Collection, utility, MilvusException
import traceback

# 상위 디렉토리를 import path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 프로젝트의 모듈 import
import config
import embedding as utils  # get_embedding (rag_server/utils.py에서 분리됨)

# 로그 디렉토리
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verification_logs")
os.makedirs(LOG_DIR, exist_ok=True)

def connect_to_milvus():
    """Milvus에 연결"""
    try:
        if not connections.has_connection("default"):
            print(f"Connecting to Milvus at {config.MILVUS_HOST}:{config.MILVUS_PORT}...")
            connections.connect("default", host=config.MILVUS_HOST, port=config.MILVUS_PORT)
            print("Successfully connected to Milvus.")
        else:
            print("Already connected to Milvus.")
        return True
    except Exception as e:
        print(f"Error connecting to Milvus: {e}")
        return False

def verify_collection_exists(collection_names: List[str]) -> Dict[str, bool]:
    """컬렉션 존재 여부 확인"""
    results = {}
    for name in collection_names:
        exists = utility.has_collection(name)
        results[name] = exists
        print(f"Collection '{name}': {'EXISTS' if exists else 'DOES NOT EXIST'}")
    return results

def sample_collection_data(collection_name: str, sample_count: int = 5) -> List[Dict]:
    """컬렉션에서 무작위 데이터 샘플링"""
    if not utility.has_collection(collection_name):
        print(f"Collection '{collection_name}' does not exist.")
        return []
    
    try:
        collection = Collection(collection_name)
        collection.load()
        
        # 필드 정보 확인
        schema = collection.schema
        print(f"\nSchema for '{collection_name}':")
        for field in schema.fields:
            print(f"  - {field.name}: {field.dtype}")
        
        # 데이터 개수 확인
        print(f"\nTotal entities in '{collection_name}': {collection.num_entities}")
        
        # 실제 데이터 샘플링
        try:
            if collection.num_entities == 0:
                print(f"Collection '{collection_name}' is empty.")
                return []
            
            # ID 값 범위 쿼리를 통한 샘플링
            results = collection.query(
                expr=f"id > 0", 
                output_fields=["*"], 
                limit=sample_count
            )
            
            print(f"\nSample {len(results)} records from '{collection_name}':")
            for i, record in enumerate(results):
                print(f"\nRecord {i+1}:")
                for k, v in record.items():
                    # 텍스트 필드는 일부만 출력
                    if isinstance(v, str) and len(v) > 100:
                        print(f"  {k}: {v[:100]}... (truncated)")
                    elif isinstance(v, (list, np.ndarray)) and len(v) > 5:
                        print(f"  {k}: [array of size {len(v)}]")
                    else:
                        print(f"  {k}: {v}")
            
            return results
            
        except Exception as query_err:
            print(f"Error querying collection: {query_err}")
            traceback.print_exc()
            
            # 대체 방법으로 검색 시도
            print("Trying alternative sampling method via search...")
            random_vector = np.random.random(config.VECTOR_DIM).astype(np.float32)
            search_results = collection.search(
                data=[random_vector.tolist()],
                anns_field="embedding",
                param=config.SEARCH_PARAMS,
                limit=sample_count,
                output_fields=["*"]
            )
            
            if search_results and search_results[0]:
                results = []
                for hit in search_results[0]:
                    try:
                        # 디버깅을 위한 로깅 추가
                        print(f"  Processing hit ID: {hit.id}")
                        entity_data = hit.entity.to_dict()
                        print(f"  Entity data keys: {list(entity_data.keys())[:5]}")
                        results.append(entity_data)
                    except Exception as hit_err:
                        print(f"Error processing hit: {hit_err}")
                
                print(f"\nSample {len(results)} records from '{collection_name}' via search:")
                for i, record in enumerate(results):
                    print(f"\nRecord {i+1}:")
                    for k, v in record.items():
                        if isinstance(v, str) and len(v) > 100:
                            print(f"  {k}: {v[:100]}... (truncated)")
                        elif isinstance(v, (list, np.ndarray)) and len(v) > 5:
                            print(f"  {k}: [array of size {len(v)}]")
                        else:
                            print(f"  {k}: {v}")
                
                return results
            else:
                print("No results from search method either.")
                return []
            
    except Exception as e:
        print(f"Error sampling collection '{collection_name}': {e}")
        traceback.print_exc()
        return []

def test_search_functionality(keywords: str, collections: List[str] = None) -> List[Dict]:
    """주어진 키워드로 검색 기능 테스트"""
    if collections is None:
        collections = config.COLLECTION_NAMES
    
    print(f"\nTesting search with keywords: '{keywords}'")
    
    # 임베딩 생성
    embedding = utils.get_embedding(keywords)
    if embedding is None:
        print("Failed to generate embedding for keywords.")
        return []
    
    # 검색 수행
    all_retrieved_chunks = []
    query_list = [embedding.tolist()]  # Milvus search expects a list of vectors

    for c_name in collections:
        print(f"\nSearching in collection: '{c_name}'...")
        if not utility.has_collection(c_name):
            print(f"  Warning: Collection '{c_name}' does not exist. Skipping.")
            continue

        if c_name not in config.COLLECTION_FIELD_MAPPINGS:
            print(f"  Warning: Field mapping for collection '{c_name}' not found in config. Skipping.")
            continue

        mapping = config.COLLECTION_FIELD_MAPPINGS[c_name]
        output_fields = mapping["output_fields"]
        text_field = mapping["text_field"]

        try:
            collection = Collection(c_name)
            # Ensure collection is loaded before searching
            if not utility.load_state(c_name) == "Loaded":
                print(f"  Loading collection '{c_name}'...")
                collection.load()
                utility.wait_for_loading_complete(c_name)
                print(f"  Collection '{c_name}' loaded.")
            else:
                print(f"  Collection '{c_name}' is already loaded.")

            print(f"  Executing search with top_k={10}...")
            search_results = collection.search(
                data=query_list,
                anns_field="embedding",  # Assuming the vector field is named 'embedding'
                param=config.SEARCH_PARAMS,
                limit=10,  # Fetch top 10 per collection
                output_fields=output_fields
            )
            print(f"  Search completed for '{c_name}'. Processing results...")

            if search_results and search_results[0]:
                for hit in search_results[0]:
                    try:
                        # 디버깅을 위한 로깅 추가
                        print(f"  Processing hit ID: {hit.id}")
                        entity_data = hit.entity.to_dict()
                        
                        # 엔티티 데이터 로깅 (처음 5개 필드만)
                        print(f"  Entity data keys: {list(entity_data.keys())[:5]}")
                        print(f"  Text field name: {text_field}")
                        
                        # 텍스트 필드가 없는 경우 직접 쿼리
                        if text_field not in entity_data or not entity_data.get(text_field):
                            print(f"  Text field '{text_field}' not found in entity or empty. Trying direct query...")
                            
                            # ID로 직접 쿼리하여 모든 필드 가져오기
                            query_result = collection.query(
                                expr=f"id == {hit.id}",
                                output_fields=["*"],
                                limit=1
                            )
                            
                            if query_result and len(query_result) > 0:
                                direct_data = query_result[0]
                                print(f"  Direct query result keys: {list(direct_data.keys())[:5]}")
                                
                                # 직접 쿼리에서 텍스트 필드 추출
                                if text_field in direct_data:
                                    entity_data[text_field] = direct_data[text_field]
                                    print(f"  Text retrieved from direct query: {entity_data[text_field][:50]}...")
                                else:
                                    print(f"  Warning: Text field '{text_field}' still not found after direct query")
                            else:
                                print(f"  Warning: No results from direct query for ID {hit.id}")
                        
                        # 텍스트 값 확인 로깅
                        text_value = entity_data.get(text_field, "")
                        print(f"  Text value type: {type(text_value)}, empty: {not bool(text_value)}")
                        if text_value:
                            print(f"  Text preview: {text_value[:50]}...")
                        else:
                            print(f"  Warning: Empty text for ID {hit.id}")
                                                        
                        chunk_data = {
                            "collection": c_name,
                            "id": hit.id,
                            "score": hit.distance,
                            "source_type": c_name,  # Default source type
                            "text": entity_data.get(text_field, "")  # Get the main text
                        }
                        # Add other metadata fields specified in output_fields
                        for field in output_fields:
                            if field != text_field and field in entity_data:
                                chunk_data[field] = entity_data[field]

                        # 디버깅용 로깅 추가
                        print(f"  Final chunk data: id={chunk_data['id']}, has_text={bool(chunk_data['text'])}")
                        all_retrieved_chunks.append(chunk_data)
                    except Exception as process_err:
                        print(f"  Warning: Error processing hit ID {getattr(hit, 'id', 'N/A')} in '{c_name}': {process_err}")
                        traceback.print_exc()
                        continue  # Skip to next hit

                print(f"  Added {len(search_results[0])} results from '{c_name}'.")
            else:
                print(f"  No results found in '{c_name}'.")

        except MilvusException as me:
            print(f"  Milvus error searching collection '{c_name}': {me}")
        except Exception as search_err:
            print(f"  Unexpected error searching collection '{c_name}': {search_err}")
            traceback.print_exc()
    
    # Sort all collected chunks by score (ascending for L2 distance) and limit
    if all_retrieved_chunks:
        all_retrieved_chunks.sort(key=lambda x: x['score'])
        print(f"\nTotal results from all collections: {len(all_retrieved_chunks)}")
        final_chunks = all_retrieved_chunks[:10]
        print(f"Returning top {len(final_chunks)} overall results.")
        
        # 로깅: 텍스트 없는 결과 카운트
        empty_text_count = sum(1 for chunk in final_chunks if not chunk.get('text'))
        if empty_text_count > 0:
            print(f"Warning: {empty_text_count} of {len(final_chunks)} results have empty text fields")
        
        # 첫 번째 결과의 텍스트 샘플 확인
        if final_chunks and final_chunks[0].get('text'):
            print(f"Sample text from first result: {final_chunks[0]['text'][:100]}...")
    
    # 검색 결과 확인
    empty_text_count = 0
    for i, item in enumerate(all_retrieved_chunks[:5]):  # 처음 5개만 상세 출력
        print(f"\nResult {i+1}:")
        print(f"  Collection: {item.get('collection')}")
        print(f"  ID: {item.get('id')}")
        print(f"  Score: {item.get('score')}")
        
        # 텍스트 필드 검사
        text = item.get('text', '')
        if not text or text.strip() == "":
            empty_text_count += 1
            print(f"  Text: [EMPTY]")
        else:
            print(f"  Text preview: {text[:100]}..." if len(text) > 100 else f"  Text: {text}")
    
    if empty_text_count > 0:
        print(f"\nWarning: {empty_text_count} out of {min(5, len(all_retrieved_chunks))} results have empty text fields!")
    
    # 결과를 파일로 저장
    timestamp = utils.get_timestamp() if hasattr(utils, 'get_timestamp') else time_now()
    output_path = os.path.join(LOG_DIR, f"search_results_{timestamp}.json")
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "keywords": keywords,
                "results_count": len(all_retrieved_chunks),
                "empty_text_count": sum(1 for r in all_retrieved_chunks if not r.get('text', '').strip()),
                "results": [
                    {
                        "id": r.get('id'),
                        "collection": r.get('collection'),
                        "score": r.get('score'),
                        "has_text": bool(r.get('text', '').strip())
                    } for r in all_retrieved_chunks
                ],
                "sample_texts": [r.get('text', '')[:200] for r in all_retrieved_chunks[:3]]
            }, f, ensure_ascii=False, indent=2)
        print(f"Search results saved to {output_path}")
    except Exception as e:
        print(f"Failed to save search results: {e}")
    
    return all_retrieved_chunks

def time_now():
    """현재 시간을 문자열로 반환"""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def run_validation():
    """전체 검증 프로세스 실행"""
    print("Starting Milvus data validation...\n")
    
    # 1. Milvus 연결
    if not connect_to_milvus():
        print("Failed to connect to Milvus. Aborting validation.")
        return
    
    # 2. 컬렉션 존재 확인
    collections = verify_collection_exists(config.COLLECTION_NAMES)
    
    # 3. 각 컬렉션 데이터 샘플링
    for collection_name in config.COLLECTION_NAMES:
        if collections.get(collection_name, False):
            print(f"\n--- Sampling data from '{collection_name}' ---")
            sample_collection_data(collection_name, sample_count=5)
    
    # 4. 검색 기능 테스트
    print("\n--- Testing search functionality ---")
    test_keywords = [
        "셀트리온 2024년 4분기 실적 재무 전략",
        "셀트리온 바이오시밀러 제품 매출",
        "셀트리온 신제품 출시 계획 전망"
    ]
    
    for keywords in test_keywords:
        test_search_functionality(keywords)
    
    print("\nMilvus data validation completed.")

if __name__ == "__main__":
    # utils 모듈에 타임스탬프 헬퍼 함수 추가
    if not hasattr(utils, 'get_timestamp'):
        from datetime import datetime
        utils.get_timestamp = lambda: datetime.now().strftime("%Y%m%d_%H%M%S")
    
    run_validation()
