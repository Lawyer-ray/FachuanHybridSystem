"""
Steering 系统集成模块

本模块实现了统一配置管理系统与 Steering 规范系统的集成，包括：
- 条件加载配置
- 缓存策略配置
- 性能监控配置
- 依赖管理配置

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging

from .manager import ConfigManager, ConfigChangeListener
from .exceptions import ConfigException
from .steering_cache_strategies import SteeringCacheStrategyManager, CacheStrategy
from .steering_performance_monitor import SteeringPerformanceMonitor
from .steering_dependency_manager import SteeringDependencyManager

logger = logging.getLogger(__name__)


@dataclass
class SteeringLoadingRule:
    """Steering 加载规则"""
    pattern: str
    condition: str  # 'always', 'fileMatch', 'manual'
    priority: int = 0
    cache_ttl: int = 3600  # 缓存生存时间（秒）
    dependencies: List[str] = field(default_factory=list)
    performance_threshold_ms: float = 100.0  # 性能阈值（毫秒）


@dataclass
class SteeringCacheConfig:
    """Steering 缓存配置"""
    enabled: bool = True
    ttl_seconds: int = 3600
    max_entries: int = 1000
    memory_limit_mb: int = 100
    auto_cleanup: bool = True
    cleanup_interval: int = 300  # 清理间隔（秒）


@dataclass
class SteeringPerformanceConfig:
    """Steering 性能配置"""
    load_threshold_ms: float = 100.0
    warn_threshold_ms: float = 500.0
    error_threshold_ms: float = 2000.0
    enable_monitoring: bool = True
    enable_profiling: bool = False
    max_concurrent_loads: int = 4


@dataclass
class SteeringDependencyConfig:
    """Steering 依赖配置"""
    auto_resolve: bool = True
    max_depth: int = 10
    circular_detection: bool = True
    load_order_strategy: str = 'priority'  # 'priority', 'dependency', 'alphabetical'


class SteeringConfigProvider:
    """Steering 配置提供者"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._cache = {}
        self._lock = threading.RLock()
    
    def get_loading_rules(self) -> List[SteeringLoadingRule]:
        """获取加载规则配置"""
        with self._lock:
            cache_key = "steering.loading_rules"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            rules = []
            
            # 从配置中读取规则
            rules_config = self.config_manager.get("steering.conditional_loading.rules", [])
            
            for rule_config in rules_config:
                rule = SteeringLoadingRule(
                    pattern=rule_config.get("pattern", ""),
                    condition=rule_config.get("condition", "manual"),
                    priority=rule_config.get("priority", 0),
                    cache_ttl=rule_config.get("cache_ttl", 3600),
                    dependencies=rule_config.get("dependencies", []),
                    performance_threshold_ms=rule_config.get("performance_threshold_ms", 100.0)
                )
                rules.append(rule)
            
            # 添加默认规则
            if not rules:
                rules = self._get_default_loading_rules()
            
            self._cache[cache_key] = rules
            return rules
    
    def get_cache_config(self) -> SteeringCacheConfig:
        """获取缓存配置"""
        with self._lock:
            cache_key = "steering.cache_config"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            config = SteeringCacheConfig(
                enabled=self.config_manager.get("steering.cache.enabled", True),
                ttl_seconds=self.config_manager.get("steering.cache.ttl_seconds", 3600),
                max_entries=self.config_manager.get("steering.cache.max_entries", 1000),
                memory_limit_mb=self.config_manager.get("steering.cache.memory_limit_mb", 100),
                auto_cleanup=self.config_manager.get("steering.cache.auto_cleanup", True),
                cleanup_interval=self.config_manager.get("steering.cache.cleanup_interval", 300)
            )
            
            self._cache[cache_key] = config
            return config
    
    def get_performance_config(self) -> SteeringPerformanceConfig:
        """获取性能配置"""
        with self._lock:
            cache_key = "steering.performance_config"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            config = SteeringPerformanceConfig(
                load_threshold_ms=self.config_manager.get("steering.performance.load_threshold_ms", 100.0),
                warn_threshold_ms=self.config_manager.get("steering.performance.warn_threshold_ms", 500.0),
                error_threshold_ms=self.config_manager.get("steering.performance.error_threshold_ms", 2000.0),
                enable_monitoring=self.config_manager.get("steering.performance.enable_monitoring", True),
                enable_profiling=self.config_manager.get("steering.performance.enable_profiling", False),
                max_concurrent_loads=self.config_manager.get("steering.performance.max_concurrent_loads", 4)
            )
            
            self._cache[cache_key] = config
            return config
    
    def get_dependency_config(self) -> SteeringDependencyConfig:
        """获取依赖配置"""
        with self._lock:
            cache_key = "steering.dependency_config"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            config = SteeringDependencyConfig(
                auto_resolve=self.config_manager.get("steering.dependencies.auto_resolve", True),
                max_depth=self.config_manager.get("steering.dependencies.max_depth", 10),
                circular_detection=self.config_manager.get("steering.dependencies.circular_detection", True),
                load_order_strategy=self.config_manager.get("steering.dependencies.load_order_strategy", "priority")
            )
            
            self._cache[cache_key] = config
            return config
    
    def _get_default_loading_rules(self) -> List[SteeringLoadingRule]:
        """获取默认加载规则"""
        return [
            # 核心规范 - 总是加载
            SteeringLoadingRule(
                pattern="core/*.md",
                condition="always",
                priority=100,
                cache_ttl=7200,  # 2小时
                performance_threshold_ms=50.0
            ),
            
            # API 层规范 - 匹配 API 文件
            SteeringLoadingRule(
                pattern="layers/api-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0
            ),
            
            # Service 层规范 - 匹配 Service 文件
            SteeringLoadingRule(
                pattern="layers/service-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0
            ),
            
            # Admin 层规范 - 匹配 Admin 文件
            SteeringLoadingRule(
                pattern="layers/admin-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0
            ),
            
            # Model 层规范 - 匹配 Model 文件
            SteeringLoadingRule(
                pattern="layers/model-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0
            ),
            
            # 模块规范 - 根据模块路径匹配
            SteeringLoadingRule(
                pattern="modules/*.md",
                condition="fileMatch",
                priority=60,
                cache_ttl=3600,
                performance_threshold_ms=150.0
            )
        ]
    
    def invalidate_cache(self, key: Optional[str] = None):
        """使缓存失效"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()


class SteeringConditionalLoader:
    """Steering 条件加载器"""
    
    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._file_pattern_cache = {}
        self._lock = threading.RLock()
    
    def should_load_specification(self, spec_file_path: str, target_file_path: str) -> bool:
        """
        判断是否应该加载指定的规范文件
        
        Args:
            spec_file_path: 规范文件路径
            target_file_path: 目标文件路径
            
        Returns:
            bool: 是否应该加载
        """
        rules = self.config_provider.get_loading_rules()
        
        for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
            if self._matches_pattern(spec_file_path, rule.pattern):
                if rule.condition == "always":
                    return True
                elif rule.condition == "fileMatch":
                    return self._matches_file_pattern(target_file_path, rule.pattern)
                elif rule.condition == "manual":
                    return False
        
        return False
    
    def get_applicable_specifications(self, target_file_path: str) -> List[str]:
        """
        获取适用于目标文件的规范文件列表
        
        Args:
            target_file_path: 目标文件路径
            
        Returns:
            List[str]: 规范文件路径列表
        """
        applicable_specs = []
        rules = self.config_provider.get_loading_rules()
        
        # 扫描所有规范文件
        steering_root = Path(".kiro/steering")
        if not steering_root.exists():
            return applicable_specs
        
        for spec_file in steering_root.rglob("*.md"):
            rel_path = spec_file.relative_to(steering_root)
            spec_path = str(rel_path)
            
            if self.should_load_specification(spec_path, target_file_path):
                applicable_specs.append(spec_path)
        
        return applicable_specs
    
    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """检查文件路径是否匹配模式"""
        import fnmatch
        return fnmatch.fnmatch(file_path, pattern)
    
    def _matches_file_pattern(self, target_file_path: str, spec_pattern: str) -> bool:
        """检查目标文件是否匹配规范的文件模式"""
        # 根据规范模式推断目标文件模式
        file_patterns = self._get_file_patterns_for_spec(spec_pattern)
        
        import fnmatch
        for pattern in file_patterns:
            if fnmatch.fnmatch(target_file_path, pattern):
                return True
        
        return False
    
    def _get_file_patterns_for_spec(self, spec_pattern: str) -> List[str]:
        """根据规范模式获取对应的文件模式"""
        with self._lock:
            if spec_pattern in self._file_pattern_cache:
                return self._file_pattern_cache[spec_pattern]
            
            patterns = []
            
            if "api-layer" in spec_pattern:
                patterns = ["**/api/**/*.py", "**/apis/**/*.py"]
            elif "service-layer" in spec_pattern:
                patterns = ["**/services/**/*.py", "**/service/**/*.py"]
            elif "admin-layer" in spec_pattern:
                patterns = ["**/admin/**/*.py", "**/admins/**/*.py"]
            elif "model-layer" in spec_pattern:
                patterns = ["**/models.py", "**/model/**/*.py"]
            elif "client-module" in spec_pattern:
                patterns = ["**/client/**/*.py", "**/clients/**/*.py"]
            elif "cases-module" in spec_pattern:
                patterns = ["**/cases/**/*.py", "**/case/**/*.py"]
            elif "contracts-module" in spec_pattern:
                patterns = ["**/contracts/**/*.py", "**/contract/**/*.py"]
            elif "organization-module" in spec_pattern:
                patterns = ["**/organization/**/*.py", "**/org/**/*.py"]
            elif "automation-module" in spec_pattern:
                patterns = ["**/automation/**/*.py", "**/auto/**/*.py"]
            elif "sms-module" in spec_pattern:
                patterns = ["**/sms/**/*.py"]
            else:
                # 默认匹配所有 Python 文件
                patterns = ["**/*.py"]
            
            self._file_pattern_cache[spec_pattern] = patterns
            return patterns


class SteeringCacheManager:
    """Steering 缓存管理器"""
    
    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._cache = {}
        self._access_times = {}
        self._lock = threading.RLock()
        self._cleanup_timer = None
        self._start_cleanup_timer()
    
    def get_cached_specification(self, spec_path: str, loader_func: Callable) -> Any:
        """获取缓存的规范"""
        cache_config = self.config_provider.get_cache_config()
        
        if not cache_config.enabled:
            return loader_func()
        
        with self._lock:
            current_time = time.time()
            
            # 检查缓存
            if spec_path in self._cache:
                cached_data, cache_time = self._cache[spec_path]
                
                # 检查是否过期
                if current_time - cache_time < cache_config.ttl_seconds:
                    self._access_times[spec_path] = current_time
                    return cached_data
                else:
                    # 过期，删除缓存
                    del self._cache[spec_path]
                    self._access_times.pop(spec_path, None)
            
            # 缓存未命中，加载数据
            data = loader_func()
            
            # 存储到缓存
            self._cache[spec_path] = (data, current_time)
            self._access_times[spec_path] = current_time
            
            # 检查缓存大小限制
            self._cleanup_if_needed(cache_config)
            
            return data
    
    def invalidate_cache(self, spec_path: Optional[str] = None):
        """使缓存失效"""
        with self._lock:
            if spec_path:
                self._cache.pop(spec_path, None)
                self._access_times.pop(spec_path, None)
            else:
                self._cache.clear()
                self._access_times.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            return {
                "cache_size": len(self._cache),
                "memory_usage_estimate": self._estimate_memory_usage(),
                "oldest_entry": min(self._access_times.values()) if self._access_times else None,
                "newest_entry": max(self._access_times.values()) if self._access_times else None
            }
    
    def _cleanup_if_needed(self, cache_config: SteeringCacheConfig):
        """根据需要清理缓存"""
        # 检查条目数量限制
        if len(self._cache) > cache_config.max_entries:
            self._cleanup_by_lru(cache_config.max_entries // 2)
        
        # 检查内存限制
        memory_usage_mb = self._estimate_memory_usage() / (1024 * 1024)
        if memory_usage_mb > cache_config.memory_limit_mb:
            self._cleanup_by_lru(len(self._cache) // 2)
    
    def _cleanup_by_lru(self, target_size: int):
        """按 LRU 策略清理缓存"""
        if len(self._cache) <= target_size:
            return
        
        # 按访问时间排序
        sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])
        
        # 删除最旧的条目
        remove_count = len(self._cache) - target_size
        for i in range(remove_count):
            spec_path = sorted_items[i][0]
            self._cache.pop(spec_path, None)
            self._access_times.pop(spec_path, None)
    
    def _estimate_memory_usage(self) -> int:
        """估算内存使用量（字节）"""
        # 简单估算：每个缓存条目约 1KB
        return len(self._cache) * 1024
    
    def _start_cleanup_timer(self):
        """启动清理定时器"""
        cache_config = self.config_provider.get_cache_config()
        
        if cache_config.auto_cleanup:
            self._cleanup_timer = threading.Timer(
                cache_config.cleanup_interval,
                self._periodic_cleanup
            )
            self._cleanup_timer.daemon = True
            self._cleanup_timer.start()
    
    def _periodic_cleanup(self):
        """定期清理"""
        try:
            cache_config = self.config_provider.get_cache_config()
            
            with self._lock:
                current_time = time.time()
                expired_keys = []
                
                # 查找过期条目
                for spec_path, (_, cache_time) in self._cache.items():
                    if current_time - cache_time > cache_config.ttl_seconds:
                        expired_keys.append(spec_path)
                
                # 删除过期条目
                for key in expired_keys:
                    self._cache.pop(key, None)
                    self._access_times.pop(key, None)
                
                if expired_keys:
                    logger.debug(f"定期清理删除了 {len(expired_keys)} 个过期缓存条目")
        
        except Exception as e:
            logger.error(f"定期清理失败: {e}")
        
        finally:
            # 重新启动定时器
            self._start_cleanup_timer()
    
    def shutdown(self):
        """关闭缓存管理器"""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()


class SteeringPerformanceMonitor:
    """Steering 性能监控器"""
    
    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._metrics = {}
        self._lock = threading.RLock()
    
    def monitor_loading(self, spec_path: str, loading_func: Callable) -> Any:
        """监控规范加载性能"""
        perf_config = self.config_provider.get_performance_config()
        
        if not perf_config.enable_monitoring:
            return loading_func()
        
        start_time = time.time()
        
        try:
            result = loading_func()
            
            # 记录成功加载
            load_time_ms = (time.time() - start_time) * 1000
            self._record_metric(spec_path, load_time_ms, True)
            
            # 检查性能阈值
            self._check_performance_thresholds(spec_path, load_time_ms, perf_config)
            
            return result
            
        except Exception as e:
            # 记录失败加载
            load_time_ms = (time.time() - start_time) * 1000
            self._record_metric(spec_path, load_time_ms, False)
            
            logger.error(f"规范加载失败 {spec_path}: {e}")
            raise
    
    def _record_metric(self, spec_path: str, load_time_ms: float, success: bool):
        """记录性能指标"""
        with self._lock:
            if spec_path not in self._metrics:
                self._metrics[spec_path] = {
                    "total_loads": 0,
                    "successful_loads": 0,
                    "failed_loads": 0,
                    "total_time_ms": 0.0,
                    "min_time_ms": float('inf'),
                    "max_time_ms": 0.0,
                    "avg_time_ms": 0.0
                }
            
            metrics = self._metrics[spec_path]
            metrics["total_loads"] += 1
            metrics["total_time_ms"] += load_time_ms
            
            if success:
                metrics["successful_loads"] += 1
            else:
                metrics["failed_loads"] += 1
            
            metrics["min_time_ms"] = min(metrics["min_time_ms"], load_time_ms)
            metrics["max_time_ms"] = max(metrics["max_time_ms"], load_time_ms)
            metrics["avg_time_ms"] = metrics["total_time_ms"] / metrics["total_loads"]
    
    def _check_performance_thresholds(self, spec_path: str, load_time_ms: float, 
                                    perf_config: SteeringPerformanceConfig):
        """检查性能阈值"""
        if load_time_ms > perf_config.error_threshold_ms:
            logger.error(f"规范加载性能严重超标 {spec_path}: {load_time_ms:.2f}ms "
                        f"(阈值: {perf_config.error_threshold_ms}ms)")
        elif load_time_ms > perf_config.warn_threshold_ms:
            logger.warning(f"规范加载性能超标 {spec_path}: {load_time_ms:.2f}ms "
                          f"(阈值: {perf_config.warn_threshold_ms}ms)")
        elif load_time_ms > perf_config.load_threshold_ms:
            logger.info(f"规范加载较慢 {spec_path}: {load_time_ms:.2f}ms "
                       f"(阈值: {perf_config.load_threshold_ms}ms)")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        with self._lock:
            return {
                "total_specifications": len(self._metrics),
                "metrics": dict(self._metrics)
            }
    
    def reset_metrics(self):
        """重置性能指标"""
        with self._lock:
            self._metrics.clear()


class SteeringDependencyResolver:
    """Steering 依赖解析器"""
    
    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._dependency_graph = {}
        self._lock = threading.RLock()
    
    def resolve_load_order(self, spec_paths: List[str]) -> List[str]:
        """
        解析加载顺序
        
        Args:
            spec_paths: 规范文件路径列表
            
        Returns:
            List[str]: 按依赖关系排序的规范文件路径列表
        """
        dep_config = self.config_provider.get_dependency_config()
        
        if not dep_config.auto_resolve:
            return spec_paths
        
        # 构建依赖图
        self._build_dependency_graph(spec_paths)
        
        # 根据策略排序
        if dep_config.load_order_strategy == "dependency":
            return self._topological_sort(spec_paths, dep_config)
        elif dep_config.load_order_strategy == "alphabetical":
            return sorted(spec_paths)
        else:  # priority
            return self._sort_by_priority(spec_paths)
    
    def _build_dependency_graph(self, spec_paths: List[str]):
        """构建依赖关系图"""
        with self._lock:
            self._dependency_graph.clear()
            
            for spec_path in spec_paths:
                dependencies = self._get_spec_dependencies(spec_path)
                self._dependency_graph[spec_path] = dependencies
    
    def _get_spec_dependencies(self, spec_path: str) -> List[str]:
        """获取规范文件的依赖"""
        try:
            full_path = Path(".kiro/steering") / spec_path
            
            if not full_path.exists():
                return []
            
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 front-matter 中的依赖信息
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    import yaml
                    try:
                        metadata = yaml.safe_load(parts[1]) or {}
                        inherits = metadata.get('inherits', [])
                        
                        if isinstance(inherits, str):
                            inherits = [inherits]
                        
                        return inherits
                    except yaml.YAMLError:
                        pass
            
            return []
            
        except Exception as e:
            logger.warning(f"获取规范依赖失败 {spec_path}: {e}")
            return []
    
    def _topological_sort(self, spec_paths: List[str], 
                         dep_config: SteeringDependencyConfig) -> List[str]:
        """拓扑排序"""
        result = []
        visited = set()
        visiting = set()
        
        def visit(spec_path: str, depth: int = 0):
            if depth > dep_config.max_depth:
                logger.warning(f"依赖深度超过限制 {spec_path}: {depth}")
                return
            
            if spec_path in visiting:
                if dep_config.circular_detection:
                    logger.warning(f"检测到循环依赖: {spec_path}")
                return
            
            if spec_path in visited:
                return
            
            visiting.add(spec_path)
            
            # 先访问依赖
            dependencies = self._dependency_graph.get(spec_path, [])
            for dep in dependencies:
                if dep in spec_paths:  # 只处理当前批次中的依赖
                    visit(dep, depth + 1)
            
            visiting.remove(spec_path)
            visited.add(spec_path)
            result.append(spec_path)
        
        for spec_path in spec_paths:
            visit(spec_path)
        
        return result
    
    def _sort_by_priority(self, spec_paths: List[str]) -> List[str]:
        """按优先级排序"""
        def get_priority(spec_path: str) -> int:
            try:
                full_path = Path(".kiro/steering") / spec_path
                
                if not full_path.exists():
                    return 0
                
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 解析 front-matter 中的优先级
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        import yaml
                        try:
                            metadata = yaml.safe_load(parts[1]) or {}
                            return metadata.get('priority', 0)
                        except yaml.YAMLError:
                            pass
                
                return 0
                
            except Exception:
                return 0
        
        return sorted(spec_paths, key=get_priority, reverse=True)


class SteeringConfigChangeListener(ConfigChangeListener):
    """Steering 配置变更监听器"""
    
    def __init__(self, config_provider: SteeringConfigProvider,
                 cache_manager: SteeringCacheManager):
        self.config_provider = config_provider
        self.cache_manager = cache_manager
    
    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """配置变更回调"""
        if key.startswith("steering."):
            logger.info(f"Steering 配置变更: {key}")
            
            # 使相关缓存失效
            if key.startswith("steering.conditional_loading"):
                self.config_provider.invalidate_cache("steering.loading_rules")
            elif key.startswith("steering.cache"):
                self.config_provider.invalidate_cache("steering.cache_config")
            elif key.startswith("steering.performance"):
                self.config_provider.invalidate_cache("steering.performance_config")
            elif key.startswith("steering.dependencies"):
                self.config_provider.invalidate_cache("steering.dependency_config")
            
            # 清空规范缓存
            self.cache_manager.invalidate_cache()
    
    def on_config_reloaded(self) -> None:
        """配置重载完成回调"""
        logger.info("Steering 配置已重载，清空所有缓存")
        self.config_provider.invalidate_cache()
        self.cache_manager.invalidate_cache()


class SteeringIntegrationManager:
    """Steering 集成管理器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        
        # 初始化组件
        self.config_provider = SteeringConfigProvider(config_manager)
        self.conditional_loader = SteeringConditionalLoader(self.config_provider)
        self.cache_manager = SteeringCacheManager(self.config_provider)
        self.dependency_resolver = SteeringDependencyResolver(self.config_provider)
        
        # 初始化高级组件
        self._init_advanced_components()
        
        # 注册配置变更监听器
        self.config_listener = SteeringConfigChangeListener(
            self.config_provider, self.cache_manager
        )
        config_manager.add_listener(self.config_listener, prefix_filter="steering.")
    
    def _init_advanced_components(self):
        """初始化高级组件"""
        # 缓存策略管理器
        cache_config = self.config_manager.get("steering.cache", {})
        self.cache_strategy_manager = SteeringCacheStrategyManager(
            CacheStrategy(cache_config.get("strategy", "smart"))
        )
        
        # 性能监控器
        perf_config = self.config_manager.get("steering.performance", {})
        self.performance_monitor = SteeringPerformanceMonitor(perf_config)
        
        # 依赖管理器
        dep_config = self.config_manager.get("steering.dependencies", {})
        self.dependency_manager = SteeringDependencyManager(dep_config)
    
    def load_specifications_for_file(self, target_file_path: str) -> List[Any]:
        """为指定文件加载相关规范"""
        # 获取适用的规范文件
        spec_paths = self.conditional_loader.get_applicable_specifications(target_file_path)
        
        if not spec_paths:
            return []
        
        # 使用依赖管理器解析加载顺序
        load_order_result = self.dependency_manager.resolve_load_order(spec_paths)
        
        # 记录依赖冲突和警告
        if load_order_result.conflicts:
            for conflict in load_order_result.conflicts:
                logger.warning(f"依赖冲突: {conflict.description}")
        
        if load_order_result.warnings:
            for warning in load_order_result.warnings:
                logger.info(f"依赖警告: {warning}")
        
        # 加载规范
        specifications = []
        for spec_path in load_order_result.ordered_specs:
            try:
                # 检查缓存
                cached_spec = self.cache_strategy_manager.get(spec_path, spec_path)
                
                if cached_spec is not None:
                    # 缓存命中，使用性能监控记录
                    spec = self.performance_monitor.monitor_cached_loading(
                        spec_path,
                        lambda: cached_spec,
                        cache_hit=True
                    )
                else:
                    # 缓存未命中，加载并缓存
                    spec = self.performance_monitor.monitor_cached_loading(
                        spec_path,
                        lambda: self._load_specification_file(spec_path),
                        cache_hit=False
                    )
                    
                    # 存储到缓存
                    self.cache_strategy_manager.put(
                        spec_path, spec, {"file_path": spec_path}
                    )
                
                specifications.append(spec)
                
            except Exception as e:
                logger.error(f"加载规范失败 {spec_path}: {e}")
        
        return specifications
    
    def _load_specification_file(self, spec_path: str) -> Any:
        """加载单个规范文件（实际加载逻辑）"""
        # 这里应该调用实际的规范加载器
        # 为了演示，返回一个简单的对象
        return {
            "path": spec_path,
            "loaded_at": time.time(),
            "content": f"规范内容: {spec_path}"
        }
    
    def get_integration_stats(self) -> Dict[str, Any]:
        """获取集成统计信息"""
        return {
            "cache_stats": self.cache_manager.get_cache_stats(),
            "cache_strategy_stats": self.cache_strategy_manager.get_stats(),
            "performance_report": self.performance_monitor.get_performance_report(),
            "dependency_stats": self.dependency_manager.get_statistics(),
            "config_provider_cache_size": len(self.config_provider._cache)
        }
    
    def export_integration_report(self, output_path: str):
        """导出集成报告"""
        try:
            report = {
                "timestamp": time.time(),
                "integration_stats": self.get_integration_stats(),
                "configuration": {
                    "cache_strategy": self.cache_strategy_manager.strategy_type.value,
                    "performance_monitoring": self.performance_monitor.enabled,
                    "dependency_auto_resolve": self.dependency_manager.auto_resolve
                }
            }
            
            import json
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"集成报告已导出到: {output_path}")
            
        except Exception as e:
            logger.error(f"导出集成报告失败: {e}")
    
    def refresh_all_caches(self):
        """刷新所有缓存"""
        self.cache_manager.invalidate_cache()
        self.cache_strategy_manager.invalidate()
        self.config_provider.invalidate_cache()
        self.dependency_manager.refresh_metadata()
        logger.info("所有 Steering 缓存已刷新")
    
    def shutdown(self):
        """关闭集成管理器"""
        self.config_manager.remove_listener(self.config_listener)
        self.cache_manager.shutdown()
        self.performance_monitor.shutdown()
        logger.info("Steering 集成管理器已关闭")