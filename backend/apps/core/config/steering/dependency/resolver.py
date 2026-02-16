"""Module for resolver."""

import logging
import threading
from collections import deque
from typing import Any

from apps.core.path import Path

from .graph import DependencyGraph
from .io import SteeringMetadataLoader
from .model import DependencyConflict, DependencyType, LoadOrderResult, LoadOrderStrategy

logger = logging.getLogger(__name__)


class SteeringDependencyManager:
    def __init__(self, config: dict[str, Any], steering_root: str = ".kiro/steering") -> None:
        self.config = config
        self.steering_root = Path(steering_root)
        self.dependency_graph = DependencyGraph()
        self._lock = threading.RLock()

        self.auto_resolve = config.get("auto_resolve", True)
        self.max_depth = config.get("max_depth", 10)
        self.circular_detection = config.get("circular_detection", True)
        self.load_order_strategy = LoadOrderStrategy(config.get("load_order_strategy", "dependency"))

        loader = SteeringMetadataLoader(steering_root=self.steering_root)
        self._metadata_cache = loader.load_all()
        for metadata in self._metadata_cache.values():
            self.dependency_graph.add_specification(metadata)

    def resolve_load_order(self, spec_paths: list[str]) -> LoadOrderResult:
        with self._lock:
            conflicts: list[DependencyConflict] = []
            warnings: list[str] = []

            conflicts.extend(self.dependency_graph.validate_dependencies(spec_paths))

            if self.circular_detection:
                cycles = self.dependency_graph.detect_circular_dependencies()
                for cycle in cycles:
                    conflicts.append(
                        DependencyConflict(
                            conflict_type="circular",
                            description=f"检测到循环依赖: {' -> '.join(cycle)}",
                            affected_specs=cycle,
                            suggested_resolution="请移除循环依赖关系",
                        )
                    )

            if self.load_order_strategy in {LoadOrderStrategy.DEPENDENCY, LoadOrderStrategy.TOPOLOGICAL}:
                ordered_specs, topo_conflicts = self.dependency_graph.topological_sort(spec_paths)
                conflicts.extend(topo_conflicts)
            elif self.load_order_strategy == LoadOrderStrategy.PRIORITY:
                ordered_specs = self._sort_by_priority(spec_paths)
            elif self.load_order_strategy == LoadOrderStrategy.ALPHABETICAL:
                ordered_specs = sorted(spec_paths)
            else:
                ordered_specs, topo_conflicts = self.dependency_graph.topological_sort(spec_paths)
                conflicts.extend(topo_conflicts)

            dependency_levels = self.dependency_graph.get_dependency_levels(ordered_specs)

            if self.auto_resolve:
                resolved_specs = self._resolve_missing_dependencies(ordered_specs)
                if len(resolved_specs) > len(ordered_specs):
                    warnings.append(f"自动添加了 {len(resolved_specs) - len(ordered_specs)} 个依赖规范")
                    ordered_specs = resolved_specs

            return LoadOrderResult(
                ordered_specs=ordered_specs,
                dependency_levels=dependency_levels,
                conflicts=conflicts,
                warnings=warnings,
                metadata={
                    "strategy": self.load_order_strategy.value,
                    "auto_resolve": self.auto_resolve,
                    "total_specs": len(ordered_specs),
                },
            )

    def _sort_by_priority(self, spec_paths: list[str]) -> list[str]:
        def get_priority(spec_path: str) -> int:
            metadata = self._metadata_cache.get(spec_path)
            return metadata.priority if metadata else 0

        return sorted(spec_paths, key=get_priority, reverse=True)

    def _resolve_missing_dependencies(self, spec_paths: list[str]) -> list[str]:
        resolved_specs = set(spec_paths)
        to_process = deque(spec_paths)
        depth = 0

        while to_process and depth < self.max_depth:
            current_spec = to_process.popleft()
            metadata = self._metadata_cache.get(current_spec)
            if not metadata:
                continue

            dependencies = self.dependency_graph.get_dependencies(
                current_spec, [DependencyType.INHERITS, DependencyType.REQUIRES]
            )
            for dep in dependencies:
                if dep.target_spec not in resolved_specs and dep.target_spec in self._metadata_cache:
                    resolved_specs.add(dep.target_spec)
                    to_process.append(dep.target_spec)
            depth += 1

        if depth >= self.max_depth:
            logger.warning(f"依赖解析达到最大深度限制: {self.max_depth}")

        return list(resolved_specs)
