"""
Steering 集成管理器

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import json
import logging
import time
from typing import Any

from apps.core.config.manager import ConfigManager
from apps.core.config.steering.performance_monitor import SteeringPerformanceMonitor
from apps.core.config.steering_cache_strategies import CacheStrategy, SteeringCacheStrategyManager
from apps.core.config.steering_dependency_manager import SteeringDependencyManager

from ._cache import SteeringCacheManager
from ._configs import SteeringConfigProvider
from ._loader import SteeringConditionalLoader
from ._resolver import SteeringConfigChangeListener, SteeringDependencyResolver

logger = logging.getLogger(__name__)

__all__ = ["SteeringIntegrationManager"]


class SteeringIntegrationManager:
    """Steering 集成管理器"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

        self.config_provider = SteeringConfigProvider(config_manager)
        self.conditional_loader = SteeringConditionalLoader(self.config_provider)
        self.cache_manager = SteeringCacheManager(self.config_provider)
        self.dependency_resolver = SteeringDependencyResolver(self.config_provider)

        self._init_advanced_components()

        self.config_listener = SteeringConfigChangeListener(self.config_provider, self.cache_manager)
        config_manager.add_listener(self.config_listener, prefix_filter="steering.")

    def _init_advanced_components(self) -> None:
        """初始化高级组件"""
        cache_config: dict[str, Any] = self.config_manager.get("steering.cache", {})
        self.cache_strategy_manager = SteeringCacheStrategyManager(CacheStrategy(cache_config.get("strategy", "smart")))

        perf_config: dict[str, Any] = self.config_manager.get("steering.performance", {})
        self.performance_monitor = SteeringPerformanceMonitor(perf_config)

        dep_config: dict[str, Any] = self.config_manager.get("steering.dependencies", {})
        self.dependency_manager = SteeringDependencyManager(dep_config)

    def load_specifications_for_file(self, target_file_path: str) -> list[Any]:
        """为指定文件加载相关规范"""
        spec_paths = self.conditional_loader.get_applicable_specifications(target_file_path)

        if not spec_paths:
            return []

        load_order_result = self.dependency_manager.resolve_load_order(spec_paths)

        if load_order_result.conflicts:
            for conflict in load_order_result.conflicts:
                logger.warning(f"依赖冲突: {conflict.description}")

        if load_order_result.warnings:
            for warning in load_order_result.warnings:
                logger.info(f"依赖警告: {warning}")

        specifications = []
        for spec_path in load_order_result.ordered_specs:
            try:
                cached_spec = self.cache_strategy_manager.get(spec_path, spec_path)

                if cached_spec is not None:
                    spec = self.performance_monitor.monitor_cached_loading(
                        spec_path, lambda: cached_spec, cache_hit=True
                    )
                else:
                    spec = self.performance_monitor.monitor_cached_loading(
                        spec_path, lambda: self._load_specification_file(spec_path), cache_hit=False
                    )
                    self.cache_strategy_manager.put(spec_path, spec, {"file_path": spec_path})

                specifications.append(spec)

            except Exception as e:
                logger.error(f"加载规范失败 {spec_path}: {e}")

        return specifications

    def _load_specification_file(self, spec_path: str) -> Any:
        """加载单个规范文件"""
        return {"path": spec_path, "loaded_at": time.time(), "content": f"规范内容: {spec_path}"}

    def get_integration_stats(self) -> dict[str, Any]:
        """获取集成统计信息"""
        return {
            "cache_stats": self.cache_manager.get_cache_stats(),
            "cache_strategy_stats": self.cache_strategy_manager.get_stats(),
            "performance_report": self.performance_monitor.get_performance_report(),
            "dependency_stats": self.dependency_manager.get_statistics(),
            "config_provider_cache_size": len(self.config_provider._cache),
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
        self.dependency_manager.refresh_metadata()
        logger.info("所有 Steering 缓存已刷新")

    def shutdown(self) -> None:
        """关闭集成管理器"""
        self.config_manager.remove_listener(self.config_listener)
        self.cache_manager.shutdown()
        self.performance_monitor.shutdown()
        logger.info("Steering 集成管理器已关闭")
