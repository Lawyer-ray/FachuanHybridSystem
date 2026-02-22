"""配置缓存模块"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0

    def touch(self) -> None:
        self.last_access = time.time()
        self.access_count += 1

    def is_expired(self, ttl: float) -> bool:
        return ttl > 0 and (time.time() - self.created_at) > ttl


class ConfigCache:
    def __init__(self, max_size: int = 1000, ttl: float = 3600.0) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired(self.ttl):
                del self._cache[key]
                return None
            entry.touch()
            return entry.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_lru()
            self._cache[key] = CacheEntry(value)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _evict_lru(self) -> None:
        if not self._cache:
            return
        lru_key = min(self._cache, key=lambda k: self._cache[k].last_access)
        del self._cache[lru_key]

    def cleanup_expired(self) -> int:
        if self.ttl <= 0:
            return 0
        with self._lock:
            expired = [k for k, e in self._cache.items() if e.is_expired(self.ttl)]
            for k in expired:
                del self._cache[k]
            return len(expired)
