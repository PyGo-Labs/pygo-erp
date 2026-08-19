"""PyGo ERP V2.0 — Cache layer.

Provides caching with Redis support.
Falls back to in-memory dict if Redis is not configured.
"""
import os
import json
import hashlib
import threading
from datetime import datetime, timedelta

base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import sys
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


# --- In-Memory Cache (fallback) ---

class MemoryCache:
    """Thread-safe in-memory cache."""
    
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
    
    def get(self, key):
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry["expires"] and datetime.utcnow() > entry["expires"]:
                del self._cache[key]
                return None
            return entry["value"]
    
    def set(self, key, value, ttl=300):
        with self._lock:
            expires = datetime.utcnow() + timedelta(seconds=ttl) if ttl else None
            self._cache[key] = {"value": value, "expires": expires}
    
    def delete(self, key):
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self):
        with self._lock:
            self._cache.clear()
    
    def keys(self):
        with self._lock:
            return list(self._cache.keys())
    
    def stats(self):
        with self._lock:
            return {"type": "memory", "entries": len(self._cache)}


# --- Redis Cache ---

class RedisCache:
    """Redis-backed cache."""
    
    def __init__(self, host="localhost", port=6379, db=0, password=None, prefix="pygo:"):
        try:
            import redis
            self.client = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
            self.prefix = prefix
            self.ping()
        except Exception as e:
            raise ConnectionError(f"Redis connection failed: {e}")
    
    def _key(self, key):
        return f"{self.prefix}{key}"
    
    def get(self, key):
        try:
            val = self.client.get(self._key(key))
            return json.loads(val) if val else None
        except Exception:
            return None
    
    def set(self, key, value, ttl=300):
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                self.client.setex(self._key(key), ttl, serialized)
            else:
                self.client.set(self._key(key), serialized)
        except Exception:
            pass
    
    def delete(self, key):
        try:
            self.client.delete(self._key(key))
        except Exception:
            pass
    
    def clear(self):
        try:
            keys = self.client.keys(f"{self.prefix}*")
            if keys:
                self.client.delete(*keys)
        except Exception:
            pass
    
    def keys(self):
        try:
            return [k.replace(self.prefix, "", 1) for k in self.client.keys(f"{self.prefix}*")]
        except Exception:
            return []
    
    def stats(self):
        try:
            info = self.client.info("memory")
            return {"type": "redis", "used_memory": info.get("used_memory_human", "N/A"), "keys": len(self.keys())}
        except Exception:
            return {"type": "redis", "error": "not available"}


# --- Cache Manager ---

class CacheManager:
    """Unified cache interface with auto-fallback."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.backend = None
        self._connect()
    
    def _connect(self):
        """Try Redis first, fallback to memory."""
        try:
            host = os.environ.get("PYGO_REDIS_HOST", "localhost")
            port = int(os.environ.get("PYGO_REDIS_PORT", "6379"))
            password = os.environ.get("PYGO_REDIS_PASS", None)
            
            # Only try Redis if PYGO_REDIS_HOST is explicitly set
            if os.environ.get("PYGO_REDIS_HOST"):
                self.backend = RedisCache(host=host, port=port, password=password)
                return
        except Exception:
            pass
        
        self.backend = MemoryCache()
    
    def get(self, key):
        return self.backend.get(key)
    
    def set(self, key, value, ttl=300):
        self.backend.set(key, value, ttl)
    
    def delete(self, key):
        self.backend.delete(key)
    
    def clear(self):
        self.backend.clear()
    
    def get_or_set(self, key, factory, ttl=300):
        """Get from cache or compute and cache."""
        val = self.get(key)
        if val is not None:
            return val
        val = factory()
        self.set(key, val, ttl)
        return val
    
    def stats(self):
        return self.backend.stats()


# --- Global cache instance ---

cache = CacheManager()


# --- Cache Handlers ---

@register("core.cache.get")
def cache_get(key=None, **kwargs):
    """Get a cache entry."""
    if not key:
        return {"error": "key required"}
    val = cache.get(key)
    return {"key": key, "value": val, "hit": val is not None}


@register("core.cache.set")
def cache_set(key=None, value=None, ttl=300, **kwargs):
    """Set a cache entry."""
    if not key:
        return {"error": "key required"}
    cache.set(key, value, ttl)
    return {"key": key, "cached": True, "ttl": ttl}


@register("core.cache.delete")
def cache_delete(key=None, **kwargs):
    """Delete a cache entry."""
    if not key:
        return {"error": "key required"}
    cache.delete(key)
    return {"deleted": True}


@register("core.cache.clear")
def cache_clear(**kwargs):
    """Clear all cache."""
    cache.clear()
    return {"cleared": True}


@register("core.cache.stats")
def cache_stats(**kwargs):
    """Get cache stats."""
    return cache.stats()


def cache_key(*args, **kwargs):
    """Generate a cache key from arguments."""
    raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()
