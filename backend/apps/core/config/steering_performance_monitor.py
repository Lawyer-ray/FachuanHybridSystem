"""
Steering 性能监控模块

本模块实现了 Steering 规范系统的性能监控功能，包括：
- 加载时间监控
- 内存使用监控
- 缓存性能监控
- 性能阈值告警
- 性能数据收集和分析

Requirements: 8.3
"""

import time
import threading
import psutil
import gc
from typing import Dict, List, Optional, Any, Callable, NamedTuple
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    value: float
    unit: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAlert:
    """性能告警"""
    level: AlertLevel
    message: str
    metric_name: str
    threshold: float
    actual_value: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadingPerformanceData:
    """加载性能数据"""
    spec_path: str
    start_time: float
    end_time: float
    duration_ms: float
    success: bool
    error_message: Optional[str] = None
    cache_hit: bool = False
    file_size_bytes: int = 0
    memory_usage_mb: float = 0.0


class PerformanceThresholds:
    """性能阈值配置"""
    
    def __init__(self, config: Dict[str, Any]):
        self.load_time_warning_ms = config.get("load_time_warning_ms", 500.0)
        self.load_time_error_ms = config.get("load_time_error_ms", 2000.0)
        self.load_time_critical_ms = config.get("load_time_critical_ms", 5000.0)
        
        self.memory_usage_warning_mb = config.get("memory_usage_warning_mb", 100.0)
        self.memory_usage_error_mb = config.get("memory_usage_error_mb", 500.0)
        self.memory_usage_critical_mb = config.get("memory_usage_critical_mb", 1000.0)
        
        self.cache_hit_rate_warning = config.get("cache_hit_rate_warning", 0.7)
        self.cache_hit_rate_error = config.get("cache_hit_rate_error", 0.5)
        
        self.concurrent_loads_warning = config.get("concurrent_loads_warning", 10)
        self.concurrent_loads_error = config.get("concurrent_loads_error", 20)


class PerformanceDataCollector:
    """性能数据收集器"""
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        self._loading_history: deque = deque(maxlen=max_history_size)
        self._metrics_history: deque = deque(maxlen=max_history_size)
        self._alerts_history: deque = deque(maxlen=max_history_size)
        self._lock = threading.RLock()
        
        # 实时统计
        self._current_loads = 0
        self._total_loads = 0
        self._successful_loads = 0
        self._failed_loads = 0
        self._cache_hits = 0
        self._cache_misses = 0
        
        # 性能统计
        self._load_times: List[float] = []
        self._memory_samples: deque = deque(maxlen=100)
        
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
    
    def record_loading_end(self, load_id: str, spec_path: str, 
                          success: bool, cache_hit: bool = False,
                          error_message: Optional[str] = None,
                          file_size_bytes: int = 0) -> LoadingPerformanceData:
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
            
            # 计算加载时间（从load_id中提取开始时间）
            try:
                start_time = float(load_id.split('_')[-1])
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
                memory_usage_mb=memory_usage_mb
            )
            
            # 存储到历史记录
            self._loading_history.append(perf_data)
            self._load_times.append(duration_ms)
            
            # 保持load_times大小限制
            if len(self._load_times) > self.max_history_size:
                self._load_times.pop(0)
            
            return perf_data
    
    def record_metric(self, metric: PerformanceMetric):
        """记录性能指标"""
        with self._lock:
            self._metrics_history.append(metric)
    
    def record_alert(self, alert: PerformanceAlert):
        """记录性能告警"""
        with self._lock:
            self._alerts_history.append(alert)
            
            # 记录日志
            log_level = {
                AlertLevel.INFO: logging.INFO,
                AlertLevel.WARNING: logging.WARNING,
                AlertLevel.ERROR: logging.ERROR,
                AlertLevel.CRITICAL: logging.CRITICAL
            }.get(alert.level, logging.INFO)
            
            logger.log(log_level, f"性能告警: {alert.message}")
    
    def get_loading_statistics(self) -> Dict[str, Any]:
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
                    "p99_ms": p99_load_time
                },
                "memory_usage_mb": self._get_current_memory_usage()
            }
    
    def get_recent_alerts(self, limit: int = 50) -> List[PerformanceAlert]:
        """获取最近的告警"""
        with self._lock:
            return list(self._alerts_history)[-limit:]
    
    def get_recent_loading_history(self, limit: int = 100) -> List[LoadingPerformanceData]:
        """获取最近的加载历史"""
        with self._lock:
            return list(self._loading_history)[-limit:]
    
    def _get_current_memory_usage(self) -> float:
        """获取当前内存使用量（MB）"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # 转换为 MB
        except Exception:
            return 0.0
    
    def _start_memory_monitoring(self):
        """启动内存监控"""
        def monitor_memory():
            while True:
                try:
                    memory_usage = self._get_current_memory_usage()
                    self._memory_samples.append(memory_usage)
                    time.sleep(5)  # 每5秒采样一次
                except Exception as e:
                    logger.error(f"内存监控失败: {e}")
                    time.sleep(10)
        
        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()


class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self, data_collector: PerformanceDataCollector,
                 thresholds: PerformanceThresholds):
        self.data_collector = data_collector
        self.thresholds = thresholds
        self._analysis_cache = {}
        self._cache_lock = threading.RLock()
    
    def analyze_loading_performance(self, spec_path: Optional[str] = None) -> Dict[str, Any]:
        """分析加载性能"""
        with self._cache_lock:
            cache_key = f"loading_analysis_{spec_path or 'all'}"
            
            # 检查缓存（5秒有效期）
            if cache_key in self._analysis_cache:
                cached_result, cache_time = self._analysis_cache[cache_key]
                if time.time() - cache_time < 5:
                    return cached_result
            
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
                "recommendations": self._generate_recommendations(history)
            }
            
            # 缓存结果
            self._analysis_cache[cache_key] = (analysis, time.time())
            
            return analysis
    
    def _analyze_performance_trend(self, history: List[LoadingPerformanceData]) -> Dict[str, Any]:
        """分析性能趋势"""
        if len(history) < 10:
            return {"trend": "insufficient_data"}
        
        # 按时间排序
        sorted_history = sorted(history, key=lambda h: h.start_time)
        
        # 计算移动平均
        window_size = min(10, len(sorted_history) // 3)
        moving_averages = []
        
        for i in range(len(sorted_history) - window_size + 1):
            window = sorted_history[i:i + window_size]
            avg_duration = sum(h.duration_ms for h in window) / len(window)
            moving_averages.append(avg_duration)
        
        if len(moving_averages) < 2:
            return {"trend": "insufficient_data"}
        
        # 计算趋势
        first_half_avg = sum(moving_averages[:len(moving_averages)//2]) / (len(moving_averages)//2)
        second_half_avg = sum(moving_averages[len(moving_averages)//2:]) / (len(moving_averages) - len(moving_averages)//2)
        
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
            "second_half_avg_ms": second_half_avg
        }
    
    def _identify_slow_specifications(self, history: List[LoadingPerformanceData]) -> List[Dict[str, Any]]:
        """识别慢规范"""
        spec_stats = defaultdict(list)
        
        for h in history:
            spec_stats[h.spec_path].append(h.duration_ms)
        
        slow_specs = []
        for spec_path, durations in spec_stats.items():
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            
            if avg_duration > self.thresholds.load_time_warning_ms:
                slow_specs.append({
                    "spec_path": spec_path,
                    "avg_duration_ms": avg_duration,
                    "max_duration_ms": max_duration,
                    "load_count": len(durations),
                    "severity": self._get_severity_level(avg_duration)
                })
        
        # 按平均时间排序
        slow_specs.sort(key=lambda x: x["avg_duration_ms"], reverse=True)
        
        return slow_specs[:10]  # 返回前10个最慢的
    
    def _analyze_error_patterns(self, history: List[LoadingPerformanceData]) -> Dict[str, Any]:
        """分析错误模式"""
        failed_loads = [h for h in history if not h.success]
        
        if not failed_loads:
            return {"total_errors": 0}
        
        # 按错误消息分组
        error_groups = defaultdict(list)
        for h in failed_loads:
            error_key = h.error_message or "unknown_error"
            error_groups[error_key].append(h)
        
        # 分析错误频率
        error_frequency = {}
        for error_msg, occurrences in error_groups.items():
            error_frequency[error_msg] = {
                "count": len(occurrences),
                "percentage": len(occurrences) / len(failed_loads) * 100,
                "affected_specs": list(set(h.spec_path for h in occurrences))
            }
        
        return {
            "total_errors": len(failed_loads),
            "error_rate": len(failed_loads) / len(history) * 100,
            "error_frequency": error_frequency
        }
    
    def _generate_recommendations(self, history: List[LoadingPerformanceData]) -> List[str]:
        """生成性能优化建议"""
        recommendations = []
        
        # 分析缓存命中率
        cache_hit_rate = sum(1 for h in history if h.cache_hit) / len(history)
        if cache_hit_rate < self.thresholds.cache_hit_rate_warning:
            recommendations.append(
                f"缓存命中率较低 ({cache_hit_rate:.1%})，建议调整缓存策略或增加缓存大小"
            )
        
        # 分析加载时间
        avg_load_time = sum(h.duration_ms for h in history) / len(history)
        if avg_load_time > self.thresholds.load_time_warning_ms:
            recommendations.append(
                f"平均加载时间较长 ({avg_load_time:.1f}ms)，建议优化规范文件大小或加载逻辑"
            )
        
        # 分析错误率
        error_rate = sum(1 for h in history if not h.success) / len(history)
        if error_rate > 0.05:  # 5% 错误率
            recommendations.append(
                f"错误率较高 ({error_rate:.1%})，建议检查规范文件完整性和加载逻辑"
            )
        
        # 分析文件大小
        large_files = [h for h in history if h.file_size_bytes > 100 * 1024]  # 100KB
        if large_files:
            recommendations.append(
                f"发现 {len(large_files)} 个大文件，建议拆分或压缩规范文件"
            )
        
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


class SteeringPerformanceMonitor:
    """Steering 性能监控器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", True)
        
        if not self.enabled:
            return
        
        self.thresholds = PerformanceThresholds(config.get("thresholds", {}))
        self.data_collector = PerformanceDataCollector(
            max_history_size=config.get("max_history_size", 1000)
        )
        self.analyzer = PerformanceAnalyzer(self.data_collector, self.thresholds)
        
        # 告警回调
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # 启动定期检查
        self._start_periodic_checks()
    
    def monitor_loading(self, spec_path: str, loading_func: Callable) -> Any:
        """监控规范加载"""
        if not self.enabled:
            return loading_func()
        
        # 记录开始
        load_id = self.data_collector.record_loading_start(spec_path)
        
        try:
            # 执行加载
            result = loading_func()
            
            # 记录成功
            perf_data = self.data_collector.record_loading_end(
                load_id, spec_path, success=True, cache_hit=False
            )
            
            # 检查性能阈值
            self._check_performance_thresholds(perf_data)
            
            return result
            
        except Exception as e:
            # 记录失败
            self.data_collector.record_loading_end(
                load_id, spec_path, success=False, 
                error_message=str(e)
            )
            raise
    
    def monitor_cached_loading(self, spec_path: str, loading_func: Callable, 
                             cache_hit: bool) -> Any:
        """监控缓存加载"""
        if not self.enabled:
            return loading_func()
        
        load_id = self.data_collector.record_loading_start(spec_path)
        
        try:
            result = loading_func()
            
            # 获取文件大小
            file_size = 0
            try:
                file_path = Path(".kiro/steering") / spec_path
                if file_path.exists():
                    file_size = file_path.stat().st_size
            except Exception:
                pass
            
            perf_data = self.data_collector.record_loading_end(
                load_id, spec_path, success=True, 
                cache_hit=cache_hit, file_size_bytes=file_size
            )
            
            self._check_performance_thresholds(perf_data)
            
            return result
            
        except Exception as e:
            self.data_collector.record_loading_end(
                load_id, spec_path, success=False, 
                cache_hit=cache_hit, error_message=str(e)
            )
            raise
    
    def _check_performance_thresholds(self, perf_data: LoadingPerformanceData):
        """检查性能阈值"""
        duration_ms = perf_data.duration_ms
        
        # 检查加载时间阈值
        if duration_ms > self.thresholds.load_time_critical_ms:
            alert = PerformanceAlert(
                level=AlertLevel.CRITICAL,
                message=f"规范加载时间严重超标: {perf_data.spec_path} ({duration_ms:.1f}ms)",
                metric_name="load_time_ms",
                threshold=self.thresholds.load_time_critical_ms,
                actual_value=duration_ms,
                timestamp=time.time(),
                metadata={"spec_path": perf_data.spec_path}
            )
            self._trigger_alert(alert)
        elif duration_ms > self.thresholds.load_time_error_ms:
            alert = PerformanceAlert(
                level=AlertLevel.ERROR,
                message=f"规范加载时间超标: {perf_data.spec_path} ({duration_ms:.1f}ms)",
                metric_name="load_time_ms",
                threshold=self.thresholds.load_time_error_ms,
                actual_value=duration_ms,
                timestamp=time.time(),
                metadata={"spec_path": perf_data.spec_path}
            )
            self._trigger_alert(alert)
        elif duration_ms > self.thresholds.load_time_warning_ms:
            alert = PerformanceAlert(
                level=AlertLevel.WARNING,
                message=f"规范加载时间较长: {perf_data.spec_path} ({duration_ms:.1f}ms)",
                metric_name="load_time_ms",
                threshold=self.thresholds.load_time_warning_ms,
                actual_value=duration_ms,
                timestamp=time.time(),
                metadata={"spec_path": perf_data.spec_path}
            )
            self._trigger_alert(alert)
        
        # 检查内存使用阈值
        memory_mb = perf_data.memory_usage_mb
        if memory_mb > self.thresholds.memory_usage_critical_mb:
            alert = PerformanceAlert(
                level=AlertLevel.CRITICAL,
                message=f"内存使用严重超标: {memory_mb:.1f}MB",
                metric_name="memory_usage_mb",
                threshold=self.thresholds.memory_usage_critical_mb,
                actual_value=memory_mb,
                timestamp=time.time()
            )
            self._trigger_alert(alert)
    
    def _trigger_alert(self, alert: PerformanceAlert):
        """触发告警"""
        self.data_collector.record_alert(alert)
        
        # 调用告警回调
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """添加告警回调"""
        self.alert_callbacks.append(callback)
    
    def get_performance_report(self) -> Dict[str, Any]:
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
                {
                    "level": alert.level.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp
                }
                for alert in recent_alerts
            ],
            "thresholds": {
                "load_time_warning_ms": self.thresholds.load_time_warning_ms,
                "load_time_error_ms": self.thresholds.load_time_error_ms,
                "memory_usage_warning_mb": self.thresholds.memory_usage_warning_mb,
                "cache_hit_rate_warning": self.thresholds.cache_hit_rate_warning
            }
        }
    
    def export_performance_data(self, file_path: str):
        """导出性能数据"""
        if not self.enabled:
            return
        
        report = self.get_performance_report()
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"性能数据已导出到: {file_path}")
        except Exception as e:
            logger.error(f"导出性能数据失败: {e}")
    
    def _start_periodic_checks(self):
        """启动定期检查"""
        def periodic_check():
            while True:
                try:
                    time.sleep(60)  # 每分钟检查一次
                    
                    # 检查缓存命中率
                    stats = self.data_collector.get_loading_statistics()
                    cache_hit_rate = stats.get("cache_hit_rate", 1.0)
                    
                    if cache_hit_rate < self.thresholds.cache_hit_rate_error:
                        alert = PerformanceAlert(
                            level=AlertLevel.ERROR,
                            message=f"缓存命中率过低: {cache_hit_rate:.1%}",
                            metric_name="cache_hit_rate",
                            threshold=self.thresholds.cache_hit_rate_error,
                            actual_value=cache_hit_rate,
                            timestamp=time.time()
                        )
                        self._trigger_alert(alert)
                    elif cache_hit_rate < self.thresholds.cache_hit_rate_warning:
                        alert = PerformanceAlert(
                            level=AlertLevel.WARNING,
                            message=f"缓存命中率较低: {cache_hit_rate:.1%}",
                            metric_name="cache_hit_rate",
                            threshold=self.thresholds.cache_hit_rate_warning,
                            actual_value=cache_hit_rate,
                            timestamp=time.time()
                        )
                        self._trigger_alert(alert)
                    
                    # 检查并发加载数
                    concurrent_loads = stats.get("current_concurrent_loads", 0)
                    if concurrent_loads > self.thresholds.concurrent_loads_error:
                        alert = PerformanceAlert(
                            level=AlertLevel.ERROR,
                            message=f"并发加载数过高: {concurrent_loads}",
                            metric_name="concurrent_loads",
                            threshold=self.thresholds.concurrent_loads_error,
                            actual_value=concurrent_loads,
                            timestamp=time.time()
                        )
                        self._trigger_alert(alert)
                    
                except Exception as e:
                    logger.error(f"定期性能检查失败: {e}")
        
        check_thread = threading.Thread(target=periodic_check, daemon=True)
        check_thread.start()
    
    def shutdown(self):
        """关闭性能监控器"""
        if self.enabled:
            logger.info("Steering 性能监控器已关闭")


def create_performance_monitor_from_config(config: Dict[str, Any]) -> SteeringPerformanceMonitor:
    """根据配置创建性能监控器"""
    return SteeringPerformanceMonitor(config)