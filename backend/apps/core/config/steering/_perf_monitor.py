"""
Steering 性能监控器

SteeringPerformanceMonitor 主类及工厂函数。
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ._perf_analyzer import PerformanceAnalyzer
from ._perf_collector import PerformanceDataCollector
from ._perf_models import AlertLevel, LoadingPerformanceData, PerformanceAlert, PerformanceThresholds

logger = logging.getLogger(__name__)


class SteeringPerformanceMonitor:
    """Steering 性能监控器"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.enabled = config.get("enabled", True)

        if not self.enabled:
            return

        self.thresholds = PerformanceThresholds(config.get("thresholds", {}))
        self.data_collector = PerformanceDataCollector(max_history_size=config.get("max_history_size", 1000))
        self.analyzer = PerformanceAnalyzer(self.data_collector, self.thresholds)
        self.alert_callbacks: list[Callable[[PerformanceAlert], None]] = []
        self._start_periodic_checks()

    def monitor_loading(self, spec_path: str, loading_func: Callable[..., Any]) -> Any:
        """监控规范加载"""
        if not self.enabled:
            return loading_func()

        load_id = self.data_collector.record_loading_start(spec_path)
        try:
            result = loading_func()
            perf_data = self.data_collector.record_loading_end(load_id, spec_path, success=True, cache_hit=False)
            self._check_performance_thresholds(perf_data)
            return result
        except Exception as e:
            self.data_collector.record_loading_end(load_id, spec_path, success=False, error_message=str(e))
            raise

    def monitor_cached_loading(self, spec_path: str, loading_func: Callable[[], Any], cache_hit: bool) -> Any:
        """监控缓存加载"""
        if not self.enabled:
            return loading_func()

        load_id = self.data_collector.record_loading_start(spec_path)
        try:
            result = loading_func()
            file_size = 0
            try:
                file_path = Path(".kiro/steering") / spec_path
                if file_path.exists():
                    file_size = file_path.stat().st_size
            except (OSError, AttributeError):
                pass

            perf_data = self.data_collector.record_loading_end(
                load_id, spec_path, success=True, cache_hit=cache_hit, file_size_bytes=file_size
            )
            self._check_performance_thresholds(perf_data)
            return result
        except Exception as e:
            self.data_collector.record_loading_end(
                load_id, spec_path, success=False, cache_hit=cache_hit, error_message=str(e)
            )
            raise

    def _check_performance_thresholds(self, perf_data: LoadingPerformanceData) -> None:
        """检查性能阈值"""
        duration_ms = perf_data.duration_ms

        if duration_ms > self.thresholds.load_time_critical_ms:
            self._trigger_alert(
                PerformanceAlert(
                    level=AlertLevel.CRITICAL,
                    message=f"规范加载时间严重超标: {perf_data.spec_path} ({duration_ms:.1f}ms)",
                    metric_name="load_time_ms",
                    threshold=self.thresholds.load_time_critical_ms,
                    actual_value=duration_ms,
                    timestamp=time.time(),
                    metadata={"spec_path": perf_data.spec_path},
                )
            )
        elif duration_ms > self.thresholds.load_time_error_ms:
            self._trigger_alert(
                PerformanceAlert(
                    level=AlertLevel.ERROR,
                    message=f"规范加载时间超标: {perf_data.spec_path} ({duration_ms:.1f}ms)",
                    metric_name="load_time_ms",
                    threshold=self.thresholds.load_time_error_ms,
                    actual_value=duration_ms,
                    timestamp=time.time(),
                    metadata={"spec_path": perf_data.spec_path},
                )
            )
        elif duration_ms > self.thresholds.load_time_warning_ms:
            self._trigger_alert(
                PerformanceAlert(
                    level=AlertLevel.WARNING,
                    message=f"规范加载时间较长: {perf_data.spec_path} ({duration_ms:.1f}ms)",
                    metric_name="load_time_ms",
                    threshold=self.thresholds.load_time_warning_ms,
                    actual_value=duration_ms,
                    timestamp=time.time(),
                    metadata={"spec_path": perf_data.spec_path},
                )
            )

        memory_mb = perf_data.memory_usage_mb
        if memory_mb > self.thresholds.memory_usage_critical_mb:
            self._trigger_alert(
                PerformanceAlert(
                    level=AlertLevel.CRITICAL,
                    message=f"内存使用严重超标: {memory_mb:.1f}MB",
                    metric_name="memory_usage_mb",
                    threshold=self.thresholds.memory_usage_critical_mb,
                    actual_value=memory_mb,
                    timestamp=time.time(),
                )
            )

    def _trigger_alert(self, alert: PerformanceAlert) -> None:
        """触发告警"""
        self.data_collector.record_alert(alert)
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except (ValueError, RuntimeError, AttributeError) as e:
                logger.error(f"告警回调失败: {e}")

    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """添加告警回调"""
        self.alert_callbacks.append(callback)

    def get_performance_report(self) -> dict[str, Any]:
        """获取性能报告"""
        if not self.enabled:
            return {"enabled": False}

        stats = self.data_collector.get_loading_statistics()
        analysis = self.analyzer.analyze_loading_performance()
        recent_alerts = self.data_collector.get_recent_alerts(20)

        return {
            "enabled": True,
            "statistics": stats,
            "analysis": analysis,
            "recent_alerts": [
                {"level": a.level.value, "message": a.message, "timestamp": a.timestamp} for a in recent_alerts
            ],
            "thresholds": {
                "load_time_warning_ms": self.thresholds.load_time_warning_ms,
                "load_time_error_ms": self.thresholds.load_time_error_ms,
                "memory_usage_warning_mb": self.thresholds.memory_usage_warning_mb,
                "cache_hit_rate_warning": self.thresholds.cache_hit_rate_warning,
            },
        }

    def export_performance_data(self, file_path: str) -> None:
        """导出性能数据"""
        if not self.enabled:
            return
        report = self.get_performance_report()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"性能数据已导出到: {file_path}")
        except (OSError, ValueError) as e:
            logger.error(f"导出性能数据失败: {e}")

    def _start_periodic_checks(self) -> None:
        """启动定期检查"""

        def periodic_check() -> None:
            while True:
                try:
                    time.sleep(60)
                    stats = self.data_collector.get_loading_statistics()
                    cache_hit_rate = stats.get("cache_hit_rate", 1.0)

                    if cache_hit_rate < self.thresholds.cache_hit_rate_error:
                        self._trigger_alert(
                            PerformanceAlert(
                                level=AlertLevel.ERROR,
                                message=f"缓存命中率过低: {cache_hit_rate:.1%}",
                                metric_name="cache_hit_rate",
                                threshold=self.thresholds.cache_hit_rate_error,
                                actual_value=cache_hit_rate,
                                timestamp=time.time(),
                            )
                        )
                    elif cache_hit_rate < self.thresholds.cache_hit_rate_warning:
                        self._trigger_alert(
                            PerformanceAlert(
                                level=AlertLevel.WARNING,
                                message=f"缓存命中率较低: {cache_hit_rate:.1%}",
                                metric_name="cache_hit_rate",
                                threshold=self.thresholds.cache_hit_rate_warning,
                                actual_value=cache_hit_rate,
                                timestamp=time.time(),
                            )
                        )

                    concurrent_loads = stats.get("current_concurrent_loads", 0)
                    if concurrent_loads > self.thresholds.concurrent_loads_error:
                        self._trigger_alert(
                            PerformanceAlert(
                                level=AlertLevel.ERROR,
                                message=f"并发加载数过高: {concurrent_loads}",
                                metric_name="concurrent_loads",
                                threshold=self.thresholds.concurrent_loads_error,
                                actual_value=concurrent_loads,
                                timestamp=time.time(),
                            )
                        )
                except (ValueError, RuntimeError) as e:
                    logger.error(f"定期性能检查失败: {e}")

        threading.Thread(target=periodic_check, daemon=True).start()

    def shutdown(self) -> None:
        """关闭性能监控器"""
        if self.enabled:
            logger.info("Steering 性能监控器已关闭")


def create_performance_monitor_from_config(config: dict[str, Any]) -> SteeringPerformanceMonitor:
    """根据配置创建性能监控器"""
    return SteeringPerformanceMonitor(config)
