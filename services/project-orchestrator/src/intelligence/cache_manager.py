from typing import Any, Dict, Optional # Added Optional
import time
import structlog

logger = structlog.get_logger()

class CacheManager:
    def __init__(self, ttl_minutes: int = 60):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_minutes * 60

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self.cache.get(key)
        if entry and (time.time() - entry["timestamp"] < self.ttl_seconds):
            logger.debug("Cache hit", key=key)
            return entry["value"]
        logger.debug("Cache miss or expired", key=key)
        return None

    def set(self, key: str, value: Dict[str, Any]):
        self.cache[key] = {"value": value, "timestamp": time.time()}
        logger.debug("Cache set", key=key)

    def invalidate(self, key: str):
        if key in self.cache:
            del self.cache[key]
            logger.debug("Cache invalidated", key=key)

    def clear(self):
        self.cache.clear()
        logger.debug("Cache cleared")

    def get_health(self) -> Dict[str, Any]:
        active_entries = sum(1 for key in self.cache if (time.time() - self.cache[key]["timestamp"] < self.ttl_seconds))
        return {
            "status": "ok",
            "total_entries": len(self.cache),
            "active_entries": active_entries,
            "ttl_seconds": self.ttl_seconds,
            "current_time": time.time()
        }
