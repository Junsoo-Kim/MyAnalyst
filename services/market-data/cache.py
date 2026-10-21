# cache.py — 크롤링 결과 Redis 캐시 (MSA 6단계에서 BE MarketDataService의 @Cacheable을 옮겨 옴)
#
# REDIS_HOST가 없거나 Redis에 닿지 못하면 캐시 없이 동작한다. 캐시는 네이버 호출을 줄이는 장치일 뿐이라
# Redis 장애가 시세·뉴스 조회 실패로 번지지 않게 한다.
import json
import os
from typing import Any, Optional

import redis

_HOST = os.getenv("REDIS_HOST", "")
_PORT = int(os.getenv("REDIS_PORT", "6379"))
_PREFIX = "market-data:"
_client: Optional[redis.Redis] = None


def _redis() -> Optional[redis.Redis]:
    global _client
    if not _HOST:
        return None
    if _client is None:
        _client = redis.Redis(host=_HOST, port=_PORT, socket_timeout=0.5, socket_connect_timeout=0.5)
    return _client


def get_json(key: str) -> Optional[Any]:
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(_PREFIX + key)
    except redis.RedisError as e:
        print(f"[cache] get 실패, 캐시 없이 진행: {e}")
        return None
    return json.loads(raw) if raw else None


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(_PREFIX + key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
    except redis.RedisError as e:
        print(f"[cache] set 실패, 무시: {e}")
