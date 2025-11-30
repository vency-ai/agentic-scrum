import time
from typing import Any, Dict

class PatternCache:
    def __init__(self, ttl_minutes: int = 30):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_minutes * 60

    def get(self, key: str) -> Any:
        entry = self.cache.get(key)
        if entry and (time.time() - entry['timestamp'] < self.ttl_seconds):
            return entry['value']
        return None

    def set(self, key: str, value: Any):
        self.cache[key] = {
            'value': value,
            'timestamp': time.time()
        }

    def invalidate(self, key: str):
        if key in self.cache:
            del self.cache[key]

    def clear(self):
        self.cache.clear()

# Global instance for use across the service
pattern_cache = PatternCache()
