"""
Steering 缓存管理器

Requirements: 8.2
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from ._configs import SteeringCacheConfig, SteeringConfigProvider

logger = logging.getLogger(__name__)

__all__ = ["SteeringCacheManager"]


class SteeringCacheManager:
    """Steering 缓存管理器"""

    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._cache: dict[str, Any] = {}
        self._access_times: dict[str, float] = {}
        self._lock = threading.RLock()
        self._cleanup_timer: threading.Timer | None = None
        self._start_cleanup_timer()

    def get_cached_specification(self, spec_path: str, loader_func: Callable[..., Any]) -> Any:
        """获取缓存的规范"""
        cache_config = self.config_provider.get_cache_config()

        if not cache_config.enabled:
            return loader_func()

        with self._lock:
            current_time = time.time()

            if spec_path in self._cache:
                cached_data, cache_time = self._cache[spec_path]

                if current_time - cache_time < cache_config.ttl_seconds:
                    self._access_times[spec_path] = current_time
                    return cached_data
                else:
                    del self._cache[spec_path]
                    self._access_times.pop(spec_path, None)

            data = loader_func()

            self._cache[spec_path] = (data, current_time)
            self._access_times[spec_path] = current_time

            self._cleanup_if_needed(cache_config)

            return data

    def invalidate_cache(self, spec_path: str | None = None) -> None:
        """使缓存失效"""
        with self._lock:
            if spec_path:
                self._cache.pop(spec_path, None)
                self._access_times.pop(spec_path, None)
            else:
                self._cache.clear()
                self._access_times.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            return {
                "cache_size": len(self._cache),
                "memory_usage_estimate": self._estimate_memory_usage(),
                "oldest_entry": min(self._access_times.values()) if self._access_times else None,
                "newest_entry": max(self._access_times.values()) if self._access_times else None,
            }

    def _cleanup_if_needed(self, cache_config: SteeringCacheConfig) -> None:
        """根据需要清理缓存"""
        if len(self._cache) > cache_config.max_entries:
            self._cleanup_by_lru(cache_config.max_entries // 2)

        memory_usage_mb = self._estimate_memory_usage() / (1024 * 1024)
        if memory_usage_mb > cache_config.memory_limit_mb:
            self._cleanup_by_lru(len(self._cache) // 2)

    def _cleanup_by_lru(self, target_size: int) -> None:
        """按 LRU 策略清理缓存"""
        if len(self._cache) <= target_size:
            return

        sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])

        remove_count = len(self._cache) - target_size
        for i in range(remove_count):
            spec_path = sorted_items[i][0]
            self._cache.pop(spec_path, None)
            self._access_times.pop(spec_path, None)

    def _estimate_memory_usage(self) -> int:
        """估算内存使用量（字节）"""
        return len(self._cache) * 1024

    def _start_cleanup_timer(self) -> None:
        """启动清理定时器"""
        cache_config = self.config_provider.get_cache_config()

        if cache_config.auto_cleanup:
            self._cleanup_timer = threading.Timer(cache_config.cleanup_interval, self._periodic_cleanup)
            self._cleanup_timer.daemon = True
            self._cleanup_timer.start()

    def _periodic_cleanup(self) -> None:
        """定期清理"""
        try:
            cache_config = self.config_provider.get_cache_config()

            with self._lock:
                current_time = time.time()
                expired_keys = []

                for spec_path, (_, cache_time) in self._cache.items():
                    if current_time - cache_time > cache_config.ttl_seconds:
                        expired_keys.append(spec_path)

                for key in expired_keys:
                    self._cache.pop(key, None)
                    self._access_times.pop(key, None)

                if expired_keys:
                    logger.debug(f"定期清理删除了 {len(expired_keys)} 个过期缓存条目")

        except Exception as e:
            logger.error(f"定期清理失败: {e}")

        finally:
            self._start_cleanup_timer()

    def shutdown(self) -> None:
        """关闭缓存管理器"""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
