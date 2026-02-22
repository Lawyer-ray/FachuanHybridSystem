"""
性能数据收集器

负责收集和存储性能监控数据，包括加载历史、指标和告警。
"""

import logging
import threading
import time
from collections import deque
from typing import Any

import psutil

from ._perf_models import AlertLevel, LoadingPerformanceData, PerformanceAlert, PerformanceMetric

logger = logging.getLogger(__name__)


class PerformanceDataCollector:
    """性能数据收集器"""

    def __init__(self, max_history_size: int = 1000) -> None:
        self.max_history_size = max_history_size
        self._loading_history: deque[Any] = deque(maxlen=max_history_size)
        self._metrics_history: deque[Any] = deque(maxlen=max_history_size)
        self._alerts_history: deque[Any] = deque(maxlen=max_history_size)
        self._lock = threading.RLock()

        # 实时统计
        self._current_loads = 0
        self._total_loads = 0
        self._successful_loads = 0
        self._failed_loads = 0
        self._cache_hits = 0
        self._cache_misses = 0

        # 性能统计
        self._load_times: list[float] = []
        self._memory_samples: deque[Any] = deque(maxlen=100)

        # 启动内存监控
        self._start_memory_monitoring()

    def record_loading_start(self, spec_path: str) -> str:
        """记录加载开始"""
        with self._lock:
            self._current_loads += 1
            self._total_loads += 1

            # 生成加载ID
            load_id = f"{spec_path}_{time.time()}"
            return load_id

    def record_loading_end(
        self,
        load_id: str,
        spec_path: str,
        success: bool,
        cache_hit: bool = False,
        error_message: str | None = None,
        file_size_bytes: int = 0,
    ) -> LoadingPerformanceData:
        """记录加载结束"""
        with self._lock:
            self._current_loads = max(0, self._current_loads - 1)

            if success:
                self._successful_loads += 1
            else:
                self._failed_loads += 1

            if cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

            # 计算加载时间(从load_id中提取开始时间)
            try:
                start_time = float(load_id.split("_")[-1])
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
            except (ValueError, IndexError):
                start_time = end_time = time.time()
                duration_ms = 0.0

            # 获取当前内存使用
            memory_usage_mb = self._get_current_memory_usage()

            # 创建性能数据
            perf_data = LoadingPerformanceData(
                spec_path=spec_path,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
                cache_hit=cache_hit,
                file_size_bytes=file_size_bytes,
                memory_usage_mb=memory_usage_mb,
            )

            # 存储到历史记录
            self._loading_history.append(perf_data)
            self._load_times.append(duration_ms)

            # 保持load_times大小限制
            if len(self._load_times) > self.max_history_size:
                self._load_times.pop(0)

            return perf_data

    def record_metric(self, metric: PerformanceMetric) -> None:
        """记录性能指标"""
        with self._lock:
            self._metrics_history.append(metric)

    def record_alert(self, alert: PerformanceAlert) -> None:
        """记录性能告警"""
        with self._lock:
            self._alerts_history.append(alert)

            # 记录日志
            log_level = {
                AlertLevel.INFO: logging.INFO,
                AlertLevel.WARNING: logging.WARNING,
                AlertLevel.ERROR: logging.ERROR,
                AlertLevel.CRITICAL: logging.CRITICAL,
            }.get(alert.level, logging.INFO)

            logger.log(log_level, f"性能告警: {alert.message}")

    def get_loading_statistics(self) -> dict[str, Any]:
        """获取加载统计信息"""
        with self._lock:
            total_requests = self._cache_hits + self._cache_misses
            cache_hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0

            success_rate = self._successful_loads / self._total_loads if self._total_loads > 0 else 0.0

            # 计算加载时间统计
            if self._load_times:
                avg_load_time = sum(self._load_times) / len(self._load_times)
                min_load_time = min(self._load_times)
                max_load_time = max(self._load_times)

                # 计算百分位数
                sorted_times = sorted(self._load_times)
                p50_index = len(sorted_times) // 2
                p95_index = int(len(sorted_times) * 0.95)
                p99_index = int(len(sorted_times) * 0.99)

                p50_load_time = sorted_times[p50_index] if sorted_times else 0.0
                p95_load_time = sorted_times[p95_index] if sorted_times else 0.0
                p99_load_time = sorted_times[p99_index] if sorted_times else 0.0
            else:
                avg_load_time = min_load_time = max_load_time = 0.0
                p50_load_time = p95_load_time = p99_load_time = 0.0

            return {
                "current_concurrent_loads": self._current_loads,
                "total_loads": self._total_loads,
                "successful_loads": self._successful_loads,
                "failed_loads": self._failed_loads,
                "success_rate": success_rate,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": cache_hit_rate,
                "load_time_stats": {
                    "avg_ms": avg_load_time,
                    "min_ms": min_load_time,
                    "max_ms": max_load_time,
                    "p50_ms": p50_load_time,
                    "p95_ms": p95_load_time,
                    "p99_ms": p99_load_time,
                },
                "memory_usage_mb": self._get_current_memory_usage(),
            }

    def get_recent_alerts(self, limit: int = 50) -> list[PerformanceAlert]:
        """获取最近的告警"""
        with self._lock:
            return list(self._alerts_history)[-limit:]

    def get_recent_loading_history(self, limit: int = 100) -> list[LoadingPerformanceData]:
        """获取最近的加载历史"""
        with self._lock:
            return list(self._loading_history)[-limit:]

    def _get_current_memory_usage(self) -> float:
        """获取当前内存使用量(MB)"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return float(memory_info.rss / (1024 * 1024))  # 转换为 MB
        except (ImportError, AttributeError, OSError):
            return 0.0

    def _start_memory_monitoring(self) -> None:
        """启动内存监控"""

        def monitor_memory() -> None:
            while True:
                try:
                    memory_usage = self._get_current_memory_usage()
                    self._memory_samples.append(memory_usage)
                    time.sleep(5)  # 每5秒采样一次
                except (OSError, ValueError, RuntimeError) as e:
                    logger.error(f"内存监控失败: {e}")
                    time.sleep(10)

        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()
