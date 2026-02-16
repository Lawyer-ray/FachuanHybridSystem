"""Module for integration provider."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from .integration_types import (
    SteeringCacheConfig,
    SteeringDependencyConfig,
    SteeringLoadingRule,
    SteeringPerformanceConfig,
)

if TYPE_CHECKING:
    from apps.core.config.manager import ConfigManager


class SteeringConfigProvider:
    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get_loading_rules(self) -> list[SteeringLoadingRule]:
        with self._lock:
            cache_key = "steering.loading_rules"
            if cache_key in self._cache:
                return self._cache[cache_key]  # type: ignore[no-any-return]

            rules = []
            rules_config: Any = self.config_manager.get("steering.conditional_loading.rules", [])
            assert isinstance(rules_config, list)

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

            if not rules:
                rules = self._get_default_loading_rules()

            self._cache[cache_key] = rules
            return rules

    def get_cache_config(self) -> SteeringCacheConfig:
        with self._lock:
            cache_key = "steering.cache_config"
            if cache_key in self._cache:
                return self._cache[cache_key]  # type: ignore[no-any-return]

            config = SteeringCacheConfig(
                enabled=self.config_manager.get("steering.cache.enabled", True) or True,
                ttl_seconds=self.config_manager.get("steering.cache.ttl_seconds", 3600) or 3600,
                max_entries=self.config_manager.get("steering.cache.max_entries", 1000) or 1000,
                memory_limit_mb=self.config_manager.get("steering.cache.memory_limit_mb", 100) or 100,
                auto_cleanup=self.config_manager.get("steering.cache.auto_cleanup", True) or True,
                cleanup_interval=self.config_manager.get("steering.cache.cleanup_interval", 300) or 300,
            )

            self._cache[cache_key] = config
            return config

    def get_performance_config(self) -> SteeringPerformanceConfig:
        with self._lock:
            cache_key = "steering.performance_config"
            if cache_key in self._cache:
                return self._cache[cache_key]  # type: ignore[no-any-return]

            config = SteeringPerformanceConfig(
                load_threshold_ms=self.config_manager.get("steering.performance.load_threshold_ms", 100.0) or 100.0,
                warn_threshold_ms=self.config_manager.get("steering.performance.warn_threshold_ms", 500.0) or 500.0,
                error_threshold_ms=self.config_manager.get("steering.performance.error_threshold_ms", 2000.0) or 2000.0,
                enable_monitoring=self.config_manager.get("steering.performance.enable_monitoring", True) or True,
                enable_profiling=self.config_manager.get("steering.performance.enable_profiling", False) or False,
                max_concurrent_loads=self.config_manager.get("steering.performance.max_concurrent_loads", 4) or 4,
            )

            self._cache[cache_key] = config
            return config

    def get_dependency_config(self) -> SteeringDependencyConfig:
        with self._lock:
            cache_key = "steering.dependency_config"
            if cache_key in self._cache:
                return self._cache[cache_key]  # type: ignore[no-any-return]

            config = SteeringDependencyConfig(
                auto_resolve=self.config_manager.get("steering.dependencies.auto_resolve", True) or True,
                max_depth=self.config_manager.get("steering.dependencies.max_depth", 10) or 10,
                circular_detection=self.config_manager.get("steering.dependencies.circular_detection", True) or True,
                load_order_strategy=self.config_manager.get("steering.dependencies.load_order_strategy", "priority")
                or "priority",
            )

            self._cache[cache_key] = config
            return config

    def _get_default_loading_rules(self) -> list[SteeringLoadingRule]:
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
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
