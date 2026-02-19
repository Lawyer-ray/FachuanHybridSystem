"""
Steering 系统配置数据类

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import threading
from dataclasses import dataclass, field
from typing import Any, cast

from apps.core.config.manager import ConfigManager

__all__ = [
    "SteeringLoadingRule",
    "SteeringCacheConfig",
    "SteeringPerformanceConfig",
    "SteeringDependencyConfig",
    "SteeringConfigProvider",
]


@dataclass
class SteeringLoadingRule:
    """Steering 加载规则"""

    pattern: str
    condition: str  # 'always', 'fileMatch', 'manual'
    priority: int = 0
    cache_ttl: int = 3600  # 缓存生存时间（秒）
    dependencies: list[str] = field(default_factory=list)
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
    load_order_strategy: str = "priority"  # 'priority', 'dependency', 'alphabetical'


class SteeringConfigProvider:
    """Steering 配置提供者"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get_loading_rules(self) -> list[SteeringLoadingRule]:
        """获取加载规则配置"""
        with self._lock:
            cache_key = "steering.loading_rules"
            if cache_key in self._cache:
                return cast(list[SteeringLoadingRule], self._cache[cache_key])

            rules: list[SteeringLoadingRule] = []

            # 从配置中读取规则
            rules_config: list[Any] = self.config_manager.get("steering.conditional_loading.rules", [])

            for rule_config in rules_config:
                rule = SteeringLoadingRule(
                    pattern=rule_config.get("pattern", ""),
                    condition=rule_config.get("condition", "manual"),
                    priority=rule_config.get("priority", 0),
                    cache_ttl=rule_config.get("cache_ttl", 3600),
                    dependencies=rule_config.get("dependencies", []),
                    performance_threshold_ms=rule_config.get("performance_threshold_ms", 100.0),
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
                return cast(SteeringCacheConfig, self._cache[cache_key])

            config = SteeringCacheConfig(
                enabled=self.config_manager.get("steering.cache.enabled", True),
                ttl_seconds=self.config_manager.get("steering.cache.ttl_seconds", 3600),
                max_entries=self.config_manager.get("steering.cache.max_entries", 1000),
                memory_limit_mb=self.config_manager.get("steering.cache.memory_limit_mb", 100),
                auto_cleanup=self.config_manager.get("steering.cache.auto_cleanup", True),
                cleanup_interval=self.config_manager.get("steering.cache.cleanup_interval", 300),
            )

            self._cache[cache_key] = config
            return config

    def get_performance_config(self) -> SteeringPerformanceConfig:
        """获取性能配置"""
        with self._lock:
            cache_key = "steering.performance_config"
            if cache_key in self._cache:
                return cast(SteeringPerformanceConfig, self._cache[cache_key])

            config = SteeringPerformanceConfig(
                load_threshold_ms=self.config_manager.get("steering.performance.load_threshold_ms", 100.0),
                warn_threshold_ms=self.config_manager.get("steering.performance.warn_threshold_ms", 500.0),
                error_threshold_ms=self.config_manager.get("steering.performance.error_threshold_ms", 2000.0),
                enable_monitoring=self.config_manager.get("steering.performance.enable_monitoring", True),
                enable_profiling=self.config_manager.get("steering.performance.enable_profiling", False),
                max_concurrent_loads=self.config_manager.get("steering.performance.max_concurrent_loads", 4),
            )

            self._cache[cache_key] = config
            return config

    def get_dependency_config(self) -> SteeringDependencyConfig:
        """获取依赖配置"""
        with self._lock:
            cache_key = "steering.dependency_config"
            if cache_key in self._cache:
                return cast(SteeringDependencyConfig, self._cache[cache_key])

            config = SteeringDependencyConfig(
                auto_resolve=self.config_manager.get("steering.dependencies.auto_resolve", True),
                max_depth=self.config_manager.get("steering.dependencies.max_depth", 10),
                circular_detection=self.config_manager.get("steering.dependencies.circular_detection", True),
                load_order_strategy=self.config_manager.get("steering.dependencies.load_order_strategy", "priority"),
            )

            self._cache[cache_key] = config
            return config

    def _get_default_loading_rules(self) -> list[SteeringLoadingRule]:
        """获取默认加载规则"""
        return [
            SteeringLoadingRule(
                pattern="core/*.md",
                condition="always",
                priority=100,
                cache_ttl=7200,
                performance_threshold_ms=50.0,
            ),
            SteeringLoadingRule(
                pattern="layers/api-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0,
            ),
            SteeringLoadingRule(
                pattern="layers/service-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0,
            ),
            SteeringLoadingRule(
                pattern="layers/admin-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0,
            ),
            SteeringLoadingRule(
                pattern="layers/model-layer.md",
                condition="fileMatch",
                priority=80,
                cache_ttl=3600,
                performance_threshold_ms=100.0,
            ),
            SteeringLoadingRule(
                pattern="modules/*.md",
                condition="fileMatch",
                priority=60,
                cache_ttl=3600,
                performance_threshold_ms=150.0,
            ),
        ]

    def invalidate_cache(self, key: str | None = None) -> None:
        """使缓存失效"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
