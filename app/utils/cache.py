# app/utils/cache.py
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
import redis.asyncio as redis
from app.config import settings

# Cache local (fallback)
_local_cache = {}

# Redis (produção)
_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        try:
            _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis.ping()
            print("✅ Redis conectado")
        except Exception:
            print("⚠️ Redis não disponível, usando cache local")
            _redis = False
    return _redis

async def cache_get(key: str) -> Optional[dict]:
    """Busca do cache (Redis → Local)"""
    # Tentar Redis
    r = await get_redis()
    if r:
        try:
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass
    
    # Fallback local
    cached = _local_cache.get(key)
    if cached:
        data, expires = cached
        if expires > datetime.now(timezone.utc):
            return data
        del _local_cache[key]
    return None

async def cache_set(key: str, data: dict, ttl_seconds: int = 300):
    """Salva no cache (Redis + Local)"""
    # Redis
    r = await get_redis()
    if r:
        try:
            await r.setex(key, ttl_seconds, json.dumps(data))
        except Exception:
            pass
    
    # Local (fallback)
    _local_cache[key] = (data, datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))

async def cache_delete(key: str):
    """Remove do cache"""
    r = await get_redis()
    if r:
        try:
            await r.delete(key)
        except Exception:
            pass
    _local_cache.pop(key, None)

async def cache_delete_pattern(pattern: str):
    """Remove todas as chaves que batem com o padrão"""
    r = await get_redis()
    if r:
        try:
            keys = await r.keys(pattern)
            if keys:
                await r.delete(*keys)
        except Exception:
            pass
    
    # Local - remove matching
    to_delete = [k for k in _local_cache if pattern.replace("*", "") in k]
    for k in to_delete:
        _local_cache.pop(k, None)