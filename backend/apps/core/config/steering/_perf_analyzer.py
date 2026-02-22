"""
性能分析器

分析性能数据，识别慢规范、错误模式，生成优化建议。
"""

import threading
import time
from collections import defaultdict
from typing import Any, cast

from ._perf_collector import PerformanceDataCollector
from ._perf_models import LoadingPerformanceData, PerformanceThresholds


class PerformanceAnalyzer:
    """性能分析器"""

    def __init__(self, data_collector: PerformanceDataCollector, thresholds: PerformanceThresholds) -> None:
        self.data_collector = data_collector
        self.thresholds = thresholds
        self._analysis_cache: dict[str, Any] = {}
        self._cache_lock = threading.RLock()

    def analyze_loading_performance(self, spec_path: str | None = None) -> dict[str, Any]:
        """分析加载性能"""
        with self._cache_lock:
            cache_key = f"loading_analysis_{spec_path or 'all'}"

            # 检查缓存(5秒有效期)
            if cache_key in self._analysis_cache:
                cached_result, cache_time = self._analysis_cache[cache_key]
                if time.time() - cache_time < 5:
                    return cast(dict[str, Any], cached_result)

            # 获取加载历史
            history = self.data_collector.get_recent_loading_history(500)

            if spec_path:
                history = [h for h in history if h.spec_path == spec_path]

            if not history:
                return {"error": "没有加载历史数据"}

            # 分析性能趋势
            analysis = {
                "total_loads": len(history),
                "success_rate": sum(1 for h in history if h.success) / len(history),
                "cache_hit_rate": sum(1 for h in history if h.cache_hit) / len(history),
                "performance_trend": self._analyze_performance_trend(history),
                "slow_specifications": self._identify_slow_specifications(history),
                "error_patterns": self._analyze_error_patterns(history),
                "recommendations": self._generate_recommendations(history),
            }

            # 缓存结果
            self._analysis_cache[cache_key] = (analysis, time.time())

            return analysis

    def _analyze_performance_trend(self, history: list[LoadingPerformanceData]) -> dict[str, Any]:
        """分析性能趋势"""
        if len(history) < 10:
            return {"trend": "insufficient_data"}

        # 按时间排序
        sorted_history = sorted(history, key=lambda h: h.start_time)

        # 计算移动平均
        window_size = min(10, len(sorted_history) // 3)
        moving_averages = []

        for i in range(len(sorted_history) - window_size + 1):
            window = sorted_history[i : i + window_size]
            avg_duration = sum(h.duration_ms for h in window) / len(window)
            moving_averages.append(avg_duration)

        if len(moving_averages) < 2:
            return {"trend": "insufficient_data"}

        # 计算趋势
        half = len(moving_averages) // 2
        first_half_avg = sum(moving_averages[:half]) / half
        second_half_avg = sum(moving_averages[half:]) / (len(moving_averages) - half)

        trend_change = (second_half_avg - first_half_avg) / first_half_avg * 100

        if trend_change > 20:
            trend = "degrading"
        elif trend_change < -20:
            trend = "improving"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "trend_change_percent": trend_change,
            "first_half_avg_ms": first_half_avg,
            "second_half_avg_ms": second_half_avg,
        }

    def _identify_slow_specifications(self, history: list[LoadingPerformanceData]) -> list[dict[str, Any]]:
        """识别慢规范"""
        spec_stats: dict[str, list[float]] = defaultdict(list)

        for h in history:
            spec_stats[h.spec_path].append(h.duration_ms)

        slow_specs = []
        for spec_path, durations in spec_stats.items():
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            if avg_duration > self.thresholds.load_time_warning_ms:
                slow_specs.append(
                    {
                        "spec_path": spec_path,
                        "avg_duration_ms": avg_duration,
                        "max_duration_ms": max_duration,
                        "load_count": len(durations),
                        "severity": self._get_severity_level(avg_duration),
                    }
                )

        # 按平均时间排序
        slow_specs.sort(key=lambda x: float(cast(float, x["avg_duration_ms"])), reverse=True)

        return slow_specs[:10]  # 返回前10个最慢的

    def _analyze_error_patterns(self, history: list[LoadingPerformanceData]) -> dict[str, Any]:
        """分析错误模式"""
        failed_loads = [h for h in history if not h.success]

        if not failed_loads:
            return {"total_errors": 0}

        # 按错误消息分组
        error_groups: dict[str, list[LoadingPerformanceData]] = defaultdict(list)
        for h in failed_loads:
            error_key = h.error_message or "unknown_error"
            error_groups[error_key].append(h)

        # 分析错误频率
        error_frequency: dict[str, Any] = {}
        for error_msg, occurrences in error_groups.items():
            error_frequency[error_msg] = {
                "count": len(occurrences),
                "percentage": len(occurrences) / len(failed_loads) * 100,
                "affected_specs": list(set(h.spec_path for h in occurrences)),
            }

        return {
            "total_errors": len(failed_loads),
            "error_rate": len(failed_loads) / len(history) * 100,
            "error_frequency": error_frequency,
        }

    def _generate_recommendations(self, history: list[LoadingPerformanceData]) -> list[str]:
        """生成性能优化建议"""
        recommendations = []

        # 分析缓存命中率
        cache_hit_rate = sum(1 for h in history if h.cache_hit) / len(history)
        if cache_hit_rate < self.thresholds.cache_hit_rate_warning:
            recommendations.append(f"缓存命中率较低 ({cache_hit_rate:.1%}),建议调整缓存策略或增加缓存大小")

        # 分析加载时间
        avg_load_time = sum(h.duration_ms for h in history) / len(history)
        if avg_load_time > self.thresholds.load_time_warning_ms:
            recommendations.append(f"平均加载时间较长 ({avg_load_time:.1f}ms),建议优化规范文件大小或加载逻辑")

        # 分析错误率
        error_rate = sum(1 for h in history if not h.success) / len(history)
        if error_rate > 0.05:  # 5% 错误率
            recommendations.append(f"错误率较高 ({error_rate:.1%}),建议检查规范文件完整性和加载逻辑")

        # 分析文件大小
        large_files = [h for h in history if h.file_size_bytes > 100 * 1024]  # 100KB
        if large_files:
            recommendations.append(f"发现 {len(large_files)} 个大文件,建议拆分或压缩规范文件")

        return recommendations

    def _get_severity_level(self, duration_ms: float) -> str:
        """获取严重程度级别"""
        if duration_ms > self.thresholds.load_time_critical_ms:
            return "critical"
        elif duration_ms > self.thresholds.load_time_error_ms:
            return "error"
        elif duration_ms > self.thresholds.load_time_warning_ms:
            return "warning"
        else:
            return "normal"
