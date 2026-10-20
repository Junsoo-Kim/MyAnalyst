"""
Milvus 컬렉션 재구축 스크립트

이 스크립트는 Milvus 컬렉션을 검사하고, 텍스트 필드가 비어있는 경우 원본 데이터를 다시 로드하여 
컬렉션을 재구축합니다.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pymilvus import connections, Collection, utility, FieldSchema, CollectionSchema
from pymilvus import DataType, MilvusException
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

# 상위 디렉토리를 import path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 프로젝트의 모듈 import
import config

# 로깅을 위한 디렉토리
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rebuild_logs")
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

def check_collection_data(collection_name: str, sample_count: int = 5) -> Dict:
    """컬렉션 데이터 상태 확인"""
    if not utility.has_collection(collection_name):
        print(f"Collection '{collection_name}' does not exist.")
        return {"exists": False}
    
    result = {"exists": True, "empty_text": False, "count": 0, "schema": {}}
    
    try:
        collection = Collection(collection_name)
        collection.load()
        
        # 스키마 정보 저장
        schema = collection.schema
        result["schema"] = {
            "name": schema.collection_name,
            "fields": [{"name": field.name, "type": str(field.dtype)} for field in schema.fields]
        }
        
        # 데이터 개수 확인
        entity_count = collection.num_entities
        result["count"] = entity_count
        
        if entity_count == 0:
            print(f"Collection '{collection_name}' is empty.")
            return result
        
        # 샘플 데이터 확인
        output_fields = ["*"]  # 모든 필드
        
        try:
            # ID 기반 쿼리로 샘플링
            query_results = collection.query(
                expr=f"id > 0", 
                output_fields=output_fields,
                limit=sample_count
            )
            
            if not query_results:
                print(f"No results returned from '{collection_name}' query.")
                result["empty_text"] = True
                return result
            
            # 텍스트 필드 확인
            text_field = config.COLLECTION_FIELD_MAPPINGS[collection_name]["text_field"]
            empty_count = 0
            
            for record in query_results:
                if not record.get(text_field) or record.get(text_field).strip() == "":
                    empty_count += 1
            
            if empty_count == len(query_results):
                print(f"Warning: All {len(query_results)} sampled records in '{collection_name}' have empty text fields.")
                result["empty_text"] = True
            elif empty_count > 0:
                print(f"Warning: {empty_count} of {len(query_results)} sampled records in '{collection_name}' have empty text fields.")
                result["empty_text"] = empty_count / len(query_results) > 0.5  # 50% 이상이 비어있으면 문제로 간주
            
            # 샘플 데이터 저장
            result["samples"] = query_results[:3]
            
            return result
            
        except Exception as e:
            print(f"Error querying collection '{collection_name}': {e}")
            result["error"] = str(e)
            return result
            
    except Exception as e:
        print(f"Error checking collection '{collection_name}': {e}")
        result["error"] = str(e)
        return result

def download_original_data(collection_name: str, output_path: str) -> bool:
    """Milvus 컬렉션의 데이터를 로컬 파일로 다운로드"""
    if not utility.has_collection(collection_name):
        print(f"Collection '{collection_name}' does not exist.")
        return False
    
    try:
        collection = Collection(collection_name)
        collection.load()
        
        # 모든 데이터 가져오기 (주의: 대용량 컬렉션은 메모리 이슈가 발생할 수 있음)
        output_fields = ["*"]
        results = collection.query(
            expr="id > 0",
            output_fields=output_fields,
            limit=collection.num_entities
        )
        
        if not results:
            print(f"No data found in collection '{collection_name}'.")
            return False
        
        # JSON 파일로 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"Successfully downloaded {len(results)} records from '{collection_name}' to {output_path}")
        return True
        
    except Exception as e:
        print(f"Error downloading data from '{collection_name}': {e}")
        return False

def rebuild_collection_from_source(collection_name: str, source_data_path: str) -> bool:
    """원본 데이터로부터 Milvus 컬렉션 재구축"""
    print(f"Rebuilding collection '{collection_name}' from {source_data_path}...")
    
    # 1. 원본 데이터 로드
    try:
        # CSV, JSON 또는 Parquet 파일 지원
        if source_data_path.endswith('.csv'):
            df = pd.read_csv(source_data_path)
        elif source_data_path.endswith('.json'):
            df = pd.read_json(source_data_path)
        elif source_data_path.endswith('.parquet'):
            df = pd.read_parquet(source_data_path)
        else:
            print(f"Unsupported file format: {source_data_path}")
            return False
        
        print(f"Loaded {len(df)} records from {source_data_path}")
        
        # 2. 필요한 필드 확인
        required_fields = ["id", "embedding"]
        if collection_name in config.COLLECTION_FIELD_MAPPINGS:
            text_field = config.COLLECTION_FIELD_MAPPINGS[collection_name]["text_field"]
            required_fields.append(text_field)
        
        for field in required_fields:
            if field not in df.columns:
                print(f"Required field '{field}' not found in source data.")
                return False
        
        # 3. 기존 컬렉션이 있으면 삭제
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)
            print(f"Dropped existing collection '{collection_name}'")
        
        # 4. 스키마 정의
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=config.VECTOR_DIM)
        ]
        
        # 텍스트 및 기타 필드 추가
        for col in df.columns:
            if col in ["id", "embedding"]:
                continue
            
            if df[col].dtype == 'object':
                fields.append(FieldSchema(name=col, dtype=DataType.VARCHAR, max_length=65535))
            elif pd.api.types.is_integer_dtype(df[col].dtype):
                fields.append(FieldSchema(name=col, dtype=DataType.INT64))
            elif pd.api.types.is_float_dtype(df[col].dtype):
                fields.append(FieldSchema(name=col, dtype=DataType.FLOAT))
            else:
                fields.append(FieldSchema(name=col, dtype=DataType.VARCHAR, max_length=65535))
        
        schema = CollectionSchema(fields=fields, description=f"Rebuilt {collection_name} collection")
        
        # 5. 컬렉션 생성
        collection = Collection(name=collection_name, schema=schema)
        print(f"Created new collection '{collection_name}'")
        
        # 6. 인덱스 생성
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            # nlist is the build-time parameter of IVF_FLAT; nprobe is a search parameter
            # (config.SEARCH_PARAMS). Passing nprobe here left nlist unset and Milvus rejected the index.
            "params": {"nlist": 128}
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        print(f"Created index on 'embedding' field")
        
        # 7. 데이터 삽입
        # 임베딩 벡터 형식 변환 (문자열 또는 리스트를 numpy 배열로)
        if isinstance(df['embedding'].iloc[0], str):
            df['embedding'] = df['embedding'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        
        insert_data = []
        for _, row in df.iterrows():
            data_dict = row.to_dict()
            # 임베딩이 NumPy 배열이면 리스트로 변환
            if isinstance(data_dict['embedding'], np.ndarray):
                data_dict['embedding'] = data_dict['embedding'].tolist()
            insert_data.append(data_dict)
        
        collection.insert(insert_data)
        collection.flush()  # 삽입 직후에는 num_entities·검색에 보이지 않는다
        print(f"Inserted {len(insert_data)} records into '{collection_name}'")
        
        # 8. 컬렉션 로드 및 카운트 확인
        collection.load()
        final_count = collection.num_entities
        print(f"Collection '{collection_name}' now has {final_count} entities.")
        
        return True
        
    except Exception as e:
        print(f"Error rebuilding collection '{collection_name}': {e}")
        import traceback
        traceback.print_exc()
        return False

def create_dummy_data(collection_name: str, count: int = 100) -> bool:
    """테스트를 위한 더미 데이터 생성 및 삽입"""
    print(f"Creating {count} dummy records for '{collection_name}'...")
    
    try:
        # 1. 기존 컬렉션이 있으면 삭제
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)
            print(f"Dropped existing collection '{collection_name}'")
        
        # 2. 스키마 정의
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=config.VECTOR_DIM)
        ]
        
        # 컬렉션별 필드 매핑에 따라 텍스트 필드 추가
        text_field = "text"
        output_fields = ["text"]
        
        if collection_name in config.COLLECTION_FIELD_MAPPINGS:
            text_field = config.COLLECTION_FIELD_MAPPINGS[collection_name]["text_field"]
            output_fields = config.COLLECTION_FIELD_MAPPINGS[collection_name]["output_fields"]
        
        # 필요한 필드 추가
        for field in output_fields:
            if field not in [f.name for f in fields]:
                fields.append(FieldSchema(name=field, dtype=DataType.VARCHAR, max_length=65535))
        
        # "title" 필드가 없으면 추가
        if "title" not in [f.name for f in fields]:
            fields.append(FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=255))
        
        schema = CollectionSchema(fields=fields, description=f"Dummy {collection_name} collection")
        
        # 3. 컬렉션 생성
        collection = Collection(name=collection_name, schema=schema)
        print(f"Created new collection '{collection_name}'")
        
        # 4. 인덱스 생성
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            # nlist is the build-time parameter of IVF_FLAT; nprobe is a search parameter
            # (config.SEARCH_PARAMS). Passing nprobe here left nlist unset and Milvus rejected the index.
            "params": {"nlist": 128}
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        print(f"Created index on 'embedding' field")
        
        # 5. 더미 데이터 생성
        dummy_data = []
        for i in range(count):
            # 임베딩 벡터 생성
            embedding = np.random.random(config.VECTOR_DIM).tolist()
            
            # 컬렉션별 더미 텍스트 생성
            if collection_name == "celltrion_embeddings":
                sample_text = f"셀트리온 바이오시밀러 제품 관련 텍스트 데이터 #{i}. 이 제품은 글로벌 시장에서 성공적으로 출시되었으며, 시장점유율을 확대하고 있습니다."
                sample_title = f"셀트리온 제품 정보 #{i}"
            else:  # news_embeddings 등
                sample_text = f"셀트리온 관련 뉴스 기사 #{i}. 셀트리온은 최근 신제품 출시 계획을 발표하고 글로벌 시장 진출을 강화하고 있습니다. 실적 개선이 기대됩니다."
                sample_title = f"셀트리온 뉴스 #{i}"
            
            # 데이터 구성
            record = {
                "id": i + 1,
                "embedding": embedding,
                text_field: sample_text,
                "title": sample_title
            }
            
            # 추가 필드 채우기
            for field in output_fields:
                if field not in record and field != text_field:
                    record[field] = f"Sample {field} data for record #{i}"
            
            dummy_data.append(record)
        
        # 6. 데이터 삽입
        collection.insert(dummy_data)
        collection.flush()  # 삽입 직후에는 num_entities·검색에 보이지 않는다
        print(f"Inserted {len(dummy_data)} dummy records into '{collection_name}'")
        
        # 7. 컬렉션 로드 및 카운트 확인
        collection.load()
        final_count = collection.num_entities
        print(f"Collection '{collection_name}' now has {final_count} entities.")
        
        return True
        
    except Exception as e:
        print(f"Error creating dummy data for '{collection_name}': {e}")
        import traceback
        traceback.print_exc()
        return False

def run_workflow():
    """전체 작업 흐름 실행"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"rebuild_log_{timestamp}.txt")
    
    # 로그 파일로 출력 리디렉션
    import sys
    original_stdout = sys.stdout
    with open(log_file, 'w', encoding='utf-8') as f:
        sys.stdout = f
        
        try:
            print(f"=== Milvus Collection Rebuild Started at {timestamp} ===")
            
            # 1. Milvus 연결
            if not connect_to_milvus():
                print("Failed to connect to Milvus. Aborting.")
                return
            
            # 2. 각 컬렉션 상태 확인
            collection_statuses = {}
            for collection_name in config.COLLECTION_NAMES:
                print(f"\n=== Checking Collection: {collection_name} ===")
                status = check_collection_data(collection_name)
                collection_statuses[collection_name] = status
                
                # 3. 문제 있는 컬렉션 처리
                if status.get("exists", False):
                    if status.get("empty_text", False):
                        print(f"\n*** Collection '{collection_name}' has empty text fields. Rebuilding... ***")
                        
                        # 3-1. 원본 데이터가 있는 경우 (경로 지정 필요)
                        source_path = input(f"Enter path to source data for '{collection_name}' (or 'dummy' for dummy data): ")
                        
                        if source_path.lower() == 'dummy':
                            create_dummy_data(collection_name)
                        elif os.path.exists(source_path):
                            rebuild_collection_from_source(collection_name, source_path)
                        else:
                            print(f"Source path '{source_path}' does not exist. Creating dummy data instead.")
                            create_dummy_data(collection_name)
                    else:
                        print(f"Collection '{collection_name}' appears to be in good condition. No action needed.")
                else:
                    print(f"\n*** Collection '{collection_name}' does not exist. Creating... ***")
                    # 3-2. 컬렉션이 없는 경우 새로 생성
                    create_dummy_data(collection_name)
            
            # 4. 검증
            print("\n=== Final Verification ===")
            for collection_name in config.COLLECTION_NAMES:
                print(f"\nVerifying collection '{collection_name}'...")
                status = check_collection_data(collection_name)
                if status.get("exists", False) and not status.get("empty_text", False):
                    print(f"Collection '{collection_name}' is now in good condition.")
                else:
                    print(f"Warning: Collection '{collection_name}' may still have issues.")
            
            print("\n=== Rebuild Process Completed ===")
            
        except Exception as e:
            print(f"Error during rebuild process: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # 표준 출력 복원
            sys.stdout = original_stdout
    
    print(f"Rebuild process completed. Log saved to {log_file}")
    # 로그 파일 내용 출력
    with open(log_file, 'r', encoding='utf-8') as f:
        print("\nLog Summary:")
        print("------------")
        for line in f.readlines()[-20:]:  # 마지막 20줄만 출력
            print(line.strip())

if __name__ == "__main__":
    # 인수 처리
    if len(sys.argv) > 1:
        if sys.argv[1] == "--create-dummy":
            # 특정 컬렉션이 지정된 경우
            if len(sys.argv) > 2:
                collection_name = sys.argv[2]
                count = int(sys.argv[3]) if len(sys.argv) > 3 else 100
                connect_to_milvus()
                create_dummy_data(collection_name, count)
            else:
                # 모든 컬렉션에 더미 데이터 생성
                connect_to_milvus()
                for collection in config.COLLECTION_NAMES:
                    create_dummy_data(collection)
        elif sys.argv[1] == "--check":
            connect_to_milvus()
            for collection in config.COLLECTION_NAMES:
                check_collection_data(collection)
    else:
        # 대화형 워크플로우 실행
        run_workflow()
