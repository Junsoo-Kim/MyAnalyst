# milvus_store.py — Milvus 연결과 Dense 벡터 검색 (rag_server/utils.py에서 분리)
from typing import Any, Dict, List

import numpy as np
from pymilvus import Collection, MilvusException, connections, utility

import config
from myanalyst_common import observability

# --- Milvus Connection Management ---
def ensure_milvus_connection():
    """Connects to Milvus if not already connected."""
    if not connections.has_connection("default"):
        print(f"Connecting to Milvus at {config.MILVUS_HOST}:{config.MILVUS_PORT}...")
        try:
            connections.connect("default", host=config.MILVUS_HOST, port=config.MILVUS_PORT)
            print("Successfully connected to Milvus.")
        except Exception as e:
            print(f"Fatal Error connecting to Milvus: {e}")
            # Exit or raise a critical error if connection fails
            raise RuntimeError(f"Could not connect to Milvus: {e}")

# --- Milvus Search Function ---
def search_milvus(query_vector: np.ndarray, collection_names_list: List[str], top_k_total: int) -> List[Dict[str, Any]]:
    """Searches multiple Milvus collections and returns merged, sorted results."""
    ensure_milvus_connection() # Ensure connection before searching
    all_retrieved_chunks = []
    query_list = [query_vector.tolist()] # Milvus search expects a list of vectors

    for c_name in collection_names_list:
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

            print(f"  Executing search with top_k={top_k_total}...")
            with observability.time_milvus_search(c_name):
                search_results = collection.search(
                    data=query_list,
                    anns_field="embedding", # Assuming the vector field is named 'embedding'
                    param=config.SEARCH_PARAMS,
                    limit=top_k_total, # Fetch enough to sort later
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

                                entity_data.update(direct_data)
                                if text_field in entity_data and entity_data.get(text_field):
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
                            "source_type": c_name, # Default source type
                            "text": entity_data.get(text_field, "") # Get the main text
                        }
                        # Add other metadata fields specified in output_fields
                        for field in output_fields:
                            if field != text_field and field in entity_data:
                                chunk_data[field] = entity_data[field]
                            # Handle potential default value overrides if schema had source_type
                            # if field == "source_type" and "source_type" in entity_data:
                            #    chunk_data["source_type"] = entity_data["source_type"]

                        # 디버깅용 로깅 추가
                        print(f"  Final chunk data: id={chunk_data['id']}, has_text={bool(chunk_data['text'])}")
                        all_retrieved_chunks.append(chunk_data)
                    except Exception as process_err:
                        print(f"  Warning: Error processing hit ID {getattr(hit, 'id', 'N/A')} in '{c_name}': {process_err}")
                        import traceback
                        traceback.print_exc()
                        continue # Skip to next hit

                print(f"  Added {len(search_results[0])} results from '{c_name}'.")
            else:
                 print(f"  No results found in '{c_name}'.")

        except MilvusException as me:
            print(f"  Milvus error searching collection '{c_name}': {me}")
        except Exception as search_err:
            print(f"  Unexpected error searching collection '{c_name}': {search_err}")
            import traceback
            traceback.print_exc()

    # Sort all collected chunks by score (ascending for L2 distance) and limit
    if all_retrieved_chunks:
        all_retrieved_chunks.sort(key=lambda x: x['score'])
        print(f"\nTotal results from all collections: {len(all_retrieved_chunks)}")
        final_chunks = all_retrieved_chunks[:top_k_total]
        print(f"Returning top {len(final_chunks)} overall results.")
        
        # 로깅: 텍스트 없는 결과 카운트
        empty_text_count = sum(1 for chunk in final_chunks if not chunk.get('text'))
        if empty_text_count > 0:
            print(f"Warning: {empty_text_count} of {len(final_chunks)} results have empty text fields")
        
        # 첫 번째 결과의 텍스트 샘플 확인
        if final_chunks and final_chunks[0].get('text'):
            print(f"Sample text from first result: {final_chunks[0]['text'][:100]}...")
        
        return final_chunks
    else:
        print("\nNo relevant chunks found across all collections.")
        return []
