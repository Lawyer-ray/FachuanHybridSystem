"""配置缓存模块"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    """缓存条目"""

    value: Any
    access_time: float = field(default_factory=time.time)
    access_count: int = 0

    def touch(self) -> None:
        """更新访问时间和次数"""
        self.access_time = time.time()
        self.access_count += 1


class ConfigCache:
    """配置缓存管理器"""

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
            if self.ttl > 0 and time.time() - entry.access_time > self.ttl:
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
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].access_time)
        del self._cache[lru_key]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_access = sum(entry.access_count for entry in self._cache.values())
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
                "total_access": total_access,
                "keys": list(self._cache.keys()),
            }

    def cleanup_expired(self) -> int:
        if self.ttl <= 0:
            return 0
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time - entry.access_time > self.ttl
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
