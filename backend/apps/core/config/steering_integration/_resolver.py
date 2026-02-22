"""
Steering 依赖解析器与配置变更监听器

Requirements: 8.3, 8.4
"""

import logging
import threading
from pathlib import Path
from typing import Any, cast

from apps.core.config.manager import ConfigChangeListener

from ._cache import SteeringCacheManager
from ._configs import SteeringConfigProvider, SteeringDependencyConfig

logger = logging.getLogger(__name__)

__all__ = ["SteeringDependencyResolver", "SteeringConfigChangeListener"]


class SteeringDependencyResolver:
    """Steering 依赖解析器"""

    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._dependency_graph: dict[str, list[str]] = {}
        self._lock = threading.RLock()

    def resolve_load_order(self, spec_paths: list[str]) -> list[str]:
        """解析加载顺序"""
        dep_config = self.config_provider.get_dependency_config()

        if not dep_config.auto_resolve:
            return spec_paths

        self._build_dependency_graph(spec_paths)

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

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    try:
                        metadata = yaml.safe_load(parts[1]) or {}
                        inherits = metadata.get("inherits", [])

                        if isinstance(inherits, str):
                            inherits = [inherits]

                        return cast(list[str], inherits)
                    except yaml.YAMLError:
                        pass

            return []

        except (OSError, ValueError, KeyError) as e:
            logger.warning(f"获取规范依赖失败 {spec_path}: {e}")
            return []

    def _topological_sort(self, spec_paths: list[str], dep_config: SteeringDependencyConfig) -> list[str]:
        """拓扑排序"""
        result: list[str] = []
        visited: set[str] = set()
        visiting: set[str] = set()

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

            dependencies = self._dependency_graph.get(spec_path, [])
            for dep in dependencies:
                if dep in spec_paths:
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

                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        import yaml

                        try:
                            metadata = yaml.safe_load(parts[1]) or {}
                            return cast(int, metadata.get("priority", 0))
                        except yaml.YAMLError:
                            pass

                return 0

            except (OSError, ValueError, IndexError):
                return 0

        return sorted(spec_paths, key=get_priority, reverse=True)


class SteeringConfigChangeListener(ConfigChangeListener):
    """Steering 配置变更监听器"""

    def __init__(self, config_provider: SteeringConfigProvider, cache_manager: SteeringCacheManager):
        self.config_provider = config_provider
        self.cache_manager = cache_manager

    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """配置变更回调"""
        if key.startswith("steering."):
            logger.info(f"Steering 配置变更: {key}")

            if key.startswith("steering.conditional_loading"):
                self.config_provider.invalidate_cache("steering.loading_rules")
            elif key.startswith("steering.cache"):
                self.config_provider.invalidate_cache("steering.cache_config")
            elif key.startswith("steering.performance"):
                self.config_provider.invalidate_cache("steering.performance_config")
            elif key.startswith("steering.dependencies"):
                self.config_provider.invalidate_cache("steering.dependency_config")

            self.cache_manager.invalidate_cache()

    def on_config_reloaded(self) -> None:
        """配置重载完成回调"""
        logger.info("Steering 配置已重载，清空所有缓存")
        self.config_provider.invalidate_cache()
        self.cache_manager.invalidate_cache()
