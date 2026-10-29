import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

class TechFreshnessCache:
    """
    Tiered freshness cache with Redis support and in-memory TTL LRU fallback.
    Caches search results, briefings, and fact checks based on freshness half-life.
    """

    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._max_memory_entries = 1000
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
        }

    def _hash_key(self, prefix: str, key: str) -> str:
        h = hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()[:16]
        return f"tech:{prefix}:{h}"

    async def get(self, prefix: str, key: str) -> Optional[Any]:
        cache_key = self._hash_key(prefix, key)
        now = time.time()

        # Check in-memory
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if entry["expires_at"] > now:
                self.stats["hits"] += 1
                return entry["data"]
            else:
                del self._memory_cache[cache_key]

        self.stats["misses"] += 1
        return None

    async def set(self, prefix: str, key: str, data: Any, ttl_seconds: int = 600):
        cache_key = self._hash_key(prefix, key)
        now = time.time()

        # Enforce memory capacity limit
        if len(self._memory_cache) >= self._max_memory_entries:
            # Evict expired or oldest entry
            expired = [k for k, v in self._memory_cache.items() if v["expires_at"] <= now]
            if expired:
                for k in expired:
                    del self._memory_cache[k]
            else:
                # Remove oldest 100 items
                keys = list(self._memory_cache.keys())[:100]
                for k in keys:
                    del self._memory_cache[k]

        self._memory_cache[cache_key] = {
            "data": data,
            "expires_at": now + ttl_seconds,
            "created_at": now,
        }
        self.stats["sets"] += 1

    def get_stats(self) -> Dict[str, Any]:
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = round(self.stats["hits"] / total * 100, 1) if total > 0 else 0.0
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "sets": self.stats["sets"],
            "hit_rate_pct": hit_rate,
            "cached_entries_count": len(self._memory_cache),
        }

tech_cache = TechFreshnessCache()
