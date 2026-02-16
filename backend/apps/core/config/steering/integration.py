"""Module for integration."""

from __future__ import annotations

"""
Steering 系统集成模块

本模块实现了统一配置管理系统与 Steering 规范系统的集成,包括:
- 条件加载配置
- 缓存策略配置
- 性能监控配置
- 依赖管理配置

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from apps.core.config.notifications import ConfigChangeListener
from apps.core.path import Path

from .cache_strategies import CacheStrategy, SteeringCacheStrategyManager
from .dependency import SteeringDependencyManager
from .integration_provider import SteeringConfigProvider
from .integration_types import SteeringCacheConfig, SteeringDependencyConfig
from .performance_monitor import SteeringPerformanceMonitor

if TYPE_CHECKING:
    from apps.core.config.manager import ConfigManager

logger = logging.getLogger(__name__)


class SteeringConditionalLoader:
    """Steering 条件加载器"""

    def __init__(self, config_provider: SteeringConfigProvider) -> None:
        self.config_provider = config_provider
        self._file_pattern_cache: dict[str, Any] = {}
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

    def get_applicable_specifications(self, target_file_path: str) -> list[str]:
        """
        获取适用于目标文件的规范文件列表

        Args:
            target_file_path: 目标文件路径

        Returns:
            List[str]: 规范文件路径列表
        """
        applicable_specs: list[str] = []

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

    _SPEC_PATTERN_MAP: ClassVar[dict[str, list[str]]] = {
        "api-layer": ["**/api/**/*.py", "**/apis/**/*.py"],
        "service-layer": ["**/services/**/*.py", "**/service/**/*.py"],
        "admin-layer": ["**/admin/**/*.py", "**/admins/**/*.py"],
        "model-layer": ["**/models.py", "**/model/**/*.py"],
        "client-module": ["**/client/**/*.py", "**/clients/**/*.py"],
        "cases-module": ["**/cases/**/*.py", "**/case/**/*.py"],
        "contracts-module": ["**/contracts/**/*.py", "**/contract/**/*.py"],
        "organization-module": ["**/organization/**/*.py", "**/org/**/*.py"],
        "automation-module": ["**/automation/**/*.py", "**/auto/**/*.py"],
        "sms-module": ["**/sms/**/*.py"],
    }

    def _get_file_patterns_for_spec(self, spec_pattern: str) -> list[str]:
        """根据规范模式获取对应的文件模式"""
        with self._lock:
            if spec_pattern in self._file_pattern_cache:
                return self._file_pattern_cache[spec_pattern]  # type: ignore[no-any-return]

            patterns = self._match_spec_patterns(spec_pattern)
            self._file_pattern_cache[spec_pattern] = patterns
            return patterns

    def _match_spec_patterns(self, spec_pattern: str) -> list[str]:
        for keyword, file_patterns in self._SPEC_PATTERN_MAP.items():
            if keyword in spec_pattern:
                return file_patterns
        return ["**/*.py"]


class SteeringCacheManager:
    """Steering 缓存管理器"""

    def __init__(self, config_provider: SteeringConfigProvider) -> None:
        self.config_provider = config_provider
        self._cache: dict[str, Any] = {}
        self._access_times: dict[str, float] = {}
        self._lock = threading.RLock()
        self._cleanup_timer: Any | None = None
        self._start_cleanup_timer()

    def get_cached_specification(self, spec_path: str, loader_func: Callable[..., Any]) -> Any:
        """获取缓存的规范"""
        cache_config: SteeringCacheConfig = self.config_provider.get_cache_config()

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
                    # 过期,删除缓存
                    del self._cache[spec_path]
                    self._access_times.pop(spec_path, None)

            # 缓存未命中,加载数据
            data = loader_func()

            # 存储到缓存
            self._cache[spec_path] = (data, current_time)
            self._access_times[spec_path] = current_time

            # 检查缓存大小限制
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
        # 检查条目数量限制
        if len(self._cache) > cache_config.max_entries:
            self._cleanup_by_lru(cache_config.max_entries // 2)

        # 检查内存限制
        memory_usage_mb = self._estimate_memory_usage() / (1024 * 1024)
        if memory_usage_mb > cache_config.memory_limit_mb:
            self._cleanup_by_lru(len(self._cache) // 2)

    def _cleanup_by_lru(self, target_size: int) -> None:
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
        """估算内存使用量(字节)"""
        # 简单估算:每个缓存条目约 1KB
        return len(self._cache) * 1024

    def _start_cleanup_timer(self) -> None:
        """启动清理定时器"""
        cache_config: SteeringCacheConfig = self.config_provider.get_cache_config()

        if cache_config.auto_cleanup:
            self._cleanup_timer = threading.Timer(cache_config.cleanup_interval, self._periodic_cleanup)
            self._cleanup_timer.daemon = True
            self._cleanup_timer.start()

    def _periodic_cleanup(self) -> None:
        """定期清理"""
        try:
            cache_config: SteeringCacheConfig = self.config_provider.get_cache_config()

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

    def shutdown(self) -> None:
        """关闭缓存管理器"""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()


class SteeringDependencyResolver:
    """Steering 依赖解析器"""

    def __init__(self, config_provider: SteeringConfigProvider) -> None:
        self.config_provider = config_provider
        self._dependency_graph: dict[str, list[str]] = {}
        self._lock = threading.RLock()

    def resolve_load_order(self, spec_paths: list[str]) -> list[str]:
        """
        解析加载顺序

        Args:
            spec_paths: 规范文件路径列表

        Returns:
            List[str]: 按依赖关系排序的规范文件路径列表
        """
        dep_config: SteeringDependencyConfig = self.config_provider.get_dependency_config()

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

    def _build_dependency_graph(self, spec_paths: list[str]) -> None:
        """构建依赖关系图"""
        with self._lock:
            self._dependency_graph.clear()

            for spec_path in spec_paths:
                dependencies = self._get_spec_dependencies(spec_path)
                self._dependency_graph[spec_path] = dependencies

    def _get_spec_dependencies(self, spec_path: str) -> list[str]:
        """获取规范文件的依赖"""
        try:
            full_path = Path(".kiro/steering") / spec_path

            if not full_path.exists():
                return []

            with open(full_path, encoding="utf-8") as f:
                content = f.read()

            # 解析 front-matter 中的依赖信息
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    try:
                        metadata = yaml.safe_load(parts[1]) or {}
                        inherits = metadata.get("inherits", [])

                        if isinstance(inherits, str):
                            inherits = [inherits]

                        return inherits  # type: ignore[no-any-return]
                    except yaml.YAMLError:
                        pass

            return []

        except Exception as e:
            logger.warning(f"获取规范依赖失败 {spec_path}: {e}")
            return []

    def _topological_sort(self, spec_paths: list[str], dep_config: SteeringDependencyConfig) -> list[str]:
        """拓扑排序"""
        result = []
        visited = set()
        visiting = set()

        def visit(spec_path: str, depth: int = 0) -> None:
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

    def _sort_by_priority(self, spec_paths: list[str]) -> list[str]:
        """按优先级排序"""

        def get_priority(spec_path: str) -> int:
            try:
                full_path = Path(".kiro/steering") / spec_path

                if not full_path.exists():
                    return 0

                with open(full_path, encoding="utf-8") as f:
                    content = f.read()

                # 解析 front-matter 中的优先级
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        import yaml

                        try:
                            metadata = yaml.safe_load(parts[1]) or {}
                            return metadata.get("priority", 0)  # type: ignore[no-any-return]
                        except yaml.YAMLError:
                            pass

                return 0

            except Exception:
                logger.exception("操作失败")

                return 0

        return sorted(spec_paths, key=get_priority, reverse=True)


class SteeringConfigChangeListener(ConfigChangeListener):
    """Steering 配置变更监听器"""

    def __init__(self, config_provider: SteeringConfigProvider, cache_manager: SteeringCacheManager) -> None:
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
        logger.info("Steering 配置已重载,清空所有缓存")
        self.config_provider.invalidate_cache()
        self.cache_manager.invalidate_cache()


class SteeringIntegrationManager:
    """Steering 集成管理器"""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager
        self.last_load_errors: list[dict[str, str]] = []

        # 初始化组件
        self.config_provider = SteeringConfigProvider(config_manager)
        self.conditional_loader = SteeringConditionalLoader(self.config_provider)
        self.cache_manager = SteeringCacheManager(self.config_provider)
        self.dependency_resolver = SteeringDependencyResolver(self.config_provider)

        # 初始化高级组件
        self._init_advanced_components()

        # 注册配置变更监听器
        self.config_listener = SteeringConfigChangeListener(self.config_provider, self.cache_manager)
        config_manager.add_listener(self.config_listener, prefix_filter="steering.")  # type: ignore[arg-type]

    def _init_advanced_components(self) -> None:
        """初始化高级组件"""
        # 缓存策略管理器
        cache_config: Any = self.config_manager.get("steering.cache", {})
        assert isinstance(cache_config, dict)
        self.cache_strategy_manager = SteeringCacheStrategyManager(CacheStrategy(cache_config.get("strategy", "smart")))

        # 性能监控器
        perf_config: Any = self.config_manager.get("steering.performance", {})
        assert isinstance(perf_config, dict)
        self.performance_monitor = SteeringPerformanceMonitor(perf_config)

        # 依赖管理器
        dep_config: Any = self.config_manager.get("steering.dependencies", {})
        assert isinstance(dep_config, dict)
        self.dependency_manager = SteeringDependencyManager(dep_config)

    def load_specifications_for_file(self, target_file_path: str) -> list[Any]:
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
        self.last_load_errors = []
        specifications = []
        for spec_path in load_order_result.ordered_specs:
            try:
                # 检查缓存
                cached_spec = self.cache_strategy_manager.get(spec_path, spec_path)

                if cached_spec is not None:
                    # 缓存命中,使用性能监控记录
                    spec = self.performance_monitor.monitor_cached_loading(
                        spec_path, lambda: cached_spec, cache_hit=True
                    )
                else:
                    # 缓存未命中,加载并缓存
                    spec = self.performance_monitor.monitor_cached_loading(
                        spec_path, lambda: self._load_specification_file(spec_path), cache_hit=False
                    )

                    # 存储到缓存
                    self.cache_strategy_manager.put(spec_path, spec, {"file_path": spec_path})

                specifications.append(spec)

            except Exception as e:
                self.last_load_errors.append({"spec_path": str(spec_path), "error_type": type(e).__name__})
                logger.warning(
                    "steering_spec_load_failed",
                    exc_info=True,
                    extra={"spec_path": str(spec_path)},
                )

        return specifications

    def _load_specification_file(self, spec_path: str) -> Any:
        """加载单个规范文件(实际加载逻辑)"""
        # 这里应该调用实际的规范加载器
        # 为了演示,返回一个简单的对象
        return {"path": spec_path, "loaded_at": time.time(), "content": f"规范内容: {spec_path}"}

    def get_integration_stats(self) -> dict[str, Any]:
        """获取集成统计信息"""
        return {
            "cache_stats": self.cache_manager.get_cache_stats(),
            "cache_strategy_stats": self.cache_strategy_manager.get_stats(),
            "performance_report": self.performance_monitor.get_performance_report(),
            "dependency_stats": getattr(self.dependency_manager, "get_statistics", lambda: {})(),
            "config_provider_cache_size": len(self.config_provider._cache),
            "last_load_errors": list[Any](self.last_load_errors),
        }

    def export_integration_report(self, output_path: str) -> None:
        """导出集成报告"""
        try:
            report = {
                "timestamp": time.time(),
                "integration_stats": self.get_integration_stats(),
                "configuration": {
                    "cache_strategy": self.cache_strategy_manager.strategy_type.value,
                    "performance_monitoring": self.performance_monitor.enabled,
                    "dependency_auto_resolve": self.dependency_manager.auto_resolve,
                },
            }

            import json

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"集成报告已导出到: {output_path}")

        except Exception as e:
            logger.error(f"导出集成报告失败: {e}")

    def refresh_all_caches(self) -> None:
        """刷新所有缓存"""
        self.cache_manager.invalidate_cache()
        self.cache_strategy_manager.invalidate()
        self.config_provider.invalidate_cache()
        if hasattr(self.dependency_manager, "refresh_metadata"):
            self.dependency_manager.refresh_metadata()
        logger.info("所有 Steering 缓存已刷新")

    def shutdown(self) -> None:
        """关闭集成管理器"""
        self.config_manager.remove_listener(self.config_listener)  # type: ignore[arg-type]
        self.cache_manager.shutdown()
        self.performance_monitor.shutdown()
        logger.info("Steering 集成管理器已关闭")
