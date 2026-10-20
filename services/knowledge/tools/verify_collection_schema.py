"""
Milvus 컬렉션의 스키마를 확인하는 도구

이 스크립트는 Milvus 컬렉션의 실제 스키마를 확인하고, 
config.py의 COLLECTION_FIELD_MAPPINGS이 올바른지 검증합니다.
"""

import os
import sys
import json
from datetime import datetime
import numpy as np
from pymilvus import connections, Collection, utility
import traceback

# 상위 디렉토리를 import path에 추가 (필요한 경우)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 프로젝트의 모듈 import
import config

# 로그 디렉토리
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# NumPy 타입을 JSON에서 직렬화 가능한 형식으로 변환하는 클래스
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

def connect_to_milvus():
    """Milvus에 연결"""
    if not connections.has_connection("default"):
        print(f"Connecting to Milvus at {config.MILVUS_HOST}:{config.MILVUS_PORT}...")
        connections.connect("default", host=config.MILVUS_HOST, port=config.MILVUS_PORT)
        print("Successfully connected to Milvus.")
    else:
        print("Already connected to Milvus.")
    return True

def get_collection_schema(collection_name):
    """컬렉션의 스키마 정보를 가져옵니다"""
    if not utility.has_collection(collection_name):
        print(f"Collection '{collection_name}' does not exist.")
        return None
    
    try:
        collection = Collection(collection_name)
        schema = collection.schema
        
        # 스키마 정보 구조화 - collection_name 속성이 없으므로 수정
        schema_info = {
            "name": collection_name,  # collection_name 대신 직접 이름 사용
            "description": getattr(schema, "description", "No description"),  # 속성이 없을 수 있으므로 getattr 사용
            "fields": []
        }
        
        for field in schema.fields:
            field_info = {
                "name": field.name,
                "type": str(field.dtype),
                "is_primary": field.is_primary,
                "description": getattr(field, "description", "")  # 속성이 없을 수 있으므로 getattr 사용
            }
            schema_info["fields"].append(field_info)
            
        return schema_info
    
    except Exception as e:
        print(f"Error getting schema for '{collection_name}': {e}")
        traceback.print_exc()
        return None

def verify_config_mappings():
    """config.py의 COLLECTION_FIELD_MAPPINGS가 실제 스키마와 일치하는지 검증"""
    connect_to_milvus()
    
    results = {}
    recommendations = {}
    
    for collection_name in config.COLLECTION_NAMES:
        print(f"\nVerifying collection: {collection_name}")
        schema_info = get_collection_schema(collection_name)
        
        if not schema_info:
            print(f"Could not get schema for '{collection_name}'")
            results[collection_name] = {"status": "error", "reason": "Schema not available"}
            continue
        
        field_names = [field["name"] for field in schema_info["fields"]]
        print(f"Available fields: {field_names}")
        
        # 현재 설정 확인
        if collection_name in config.COLLECTION_FIELD_MAPPINGS:
            mapping = config.COLLECTION_FIELD_MAPPINGS[collection_name]
            current_text_field = mapping.get("text_field")  # text_field 변수 명확하게 선언
            output_fields = mapping.get("output_fields", [])
            
            issues = []
            
            # 텍스트 필드 검증
            if current_text_field not in field_names:
                issues.append(f"Specified text_field '{current_text_field}' does not exist in schema")
                # 대안 찾기
                text_alternatives = [f for f in field_names if any(keyword in f.lower() for keyword in ["text", "content", "body", "chunk", "article"])]
                if not text_alternatives:
                    text_alternatives = field_names  # 모든 필드를 후보로
            else:
                text_alternatives = []
            
            # 출력 필드 검증
            invalid_fields = [f for f in output_fields if f not in field_names]
            if invalid_fields:
                issues.append(f"These output_fields don't exist in schema: {invalid_fields}")
            
            # 검증 결과
            if issues:
                results[collection_name] = {"status": "issues", "issues": issues}
                
                # 권장 매핑 생성
                recommended_text_field = current_text_field  # 현재 값 유지
                if current_text_field not in field_names and text_alternatives:
                    recommended_text_field = text_alternatives[0]
                
                recommended_output_fields = [f for f in output_fields if f in field_names]
                # 누락된 유용한 필드 추가
                for field in field_names:
                    if field not in recommended_output_fields:
                        if any(keyword in field.lower() for keyword in ["text", "title", "content", "summary", "chunk"]):
                            recommended_output_fields.append(field)
                
                recommendations[collection_name] = {
                    "text_field": recommended_text_field,
                    "output_fields": recommended_output_fields
                }
            else:
                results[collection_name] = {"status": "ok"}
        else:
            results[collection_name] = {"status": "missing", "reason": "No mapping defined in config"}
            
            # 기본 매핑 추천
            text_alternatives = [f for f in field_names if any(keyword in f.lower() for keyword in ["text", "content", "body", "chunk", "article"])]
            recommended_text_field = text_alternatives[0] if text_alternatives else field_names[0]
            
            recommended_output_fields = []
            for field in field_names:
                if any(keyword in field.lower() for keyword in ["id", "text", "title", "content", "summary", "chunk"]):
                    recommended_output_fields.append(field)
            
            recommendations[collection_name] = {
                "text_field": recommended_text_field,
                "output_fields": recommended_output_fields
            }
    
    # 샘플 데이터 쿼리하여 실제 값 확인
    for collection_name in config.COLLECTION_NAMES:
        print(f"\nFetching sample data from {collection_name}...")
        if utility.has_collection(collection_name):
            try:
                collection = Collection(collection_name)
                collection.load()
                
                # 샘플 데이터 가져오기
                query_results = collection.query(
                    expr="id > 0",
                    output_fields=["*"],
                    limit=2
                )
                
                if query_results:
                    print(f"Sample data from {collection_name}:")
                    for record in query_results:
                        print(f"ID: {record.get('id')}")
                        
                        # 해당 collection에 권장 설정이 있을 경우
                        if collection_name in recommendations:
                            rec_text_field = recommendations[collection_name]["text_field"]
                            if rec_text_field in record:
                                text_value = record[rec_text_field]
                                print(f"{rec_text_field}: {type(text_value)} - {text_value[:100]}..." if isinstance(text_value, str) and len(text_value) > 100 else f"{rec_text_field}: {text_value}")
                        
                        # 다른 필드 정보
                        for field, value in record.items():
                            # text_field가 정의되지 않을 수 있으므로 조건 수정
                            if isinstance(value, str) and (collection_name not in recommendations or field != recommendations[collection_name]["text_field"]):
                                print(f"{field}: {value[:50]}..." if len(value) > 50 else f"{field}: {value}")
                else:
                    print(f"No data found in {collection_name}")
            except Exception as e:
                print(f"Error querying {collection_name}: {e}")
                traceback.print_exc()
    
    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"schema_verification_{timestamp}.json")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "verification_results": results,
                "recommendations": recommendations
            }, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)  # NumPy 인코더 사용
        
        print(f"\nVerification results saved to {log_path}")
    except Exception as e:
        print(f"Error saving results: {e}")
        traceback.print_exc()
    
    # 권장 매핑 출력
    if recommendations:
        print("\nRecommended COLLECTION_FIELD_MAPPINGS:")
        print("```python")
        print("COLLECTION_FIELD_MAPPINGS = {")
        for collection_name, mapping in recommendations.items():
            print(f"    \"{collection_name}\": {{")
            print(f"        \"text_field\": \"{mapping['text_field']}\",")
            print(f"        \"output_fields\": {mapping['output_fields']}")
            print("    },")
        print("}")
        print("```")

if __name__ == "__main__":
    verify_config_mappings()
