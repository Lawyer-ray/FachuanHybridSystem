"""Module for graph."""

from __future__ import annotations

import threading
from collections import defaultdict, deque

from .model import DependencyConflict, DependencyInfo, DependencyType, SpecificationMetadata


class DependencyGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, SpecificationMetadata] = {}
        self.edges: dict[str, list[DependencyInfo]] = defaultdict(list)
        self.reverse_edges: dict[str, list[DependencyInfo]] = defaultdict(list)
        self._lock = threading.RLock()

    def add_specification(self, metadata: SpecificationMetadata) -> None:
        with self._lock:
            self.nodes[metadata.path] = metadata
            self._add_dependency_edges(metadata)

    def _add_dependency_edges(self, metadata: SpecificationMetadata) -> None:
        for dep in metadata.inherits:
            self._add_edge(metadata.path, dep, DependencyType.INHERITS)
        for dep in metadata.requires:
            self._add_edge(metadata.path, dep, DependencyType.REQUIRES)
        for dep in metadata.optional_deps:
            self._add_edge(metadata.path, dep, DependencyType.OPTIONAL)
        for dep in metadata.conflicts:
            self._add_edge(metadata.path, dep, DependencyType.CONFLICTS)

    def _add_edge(self, source: str, target: str, dep_type: DependencyType) -> None:
        info = DependencyInfo(source_spec=source, target_spec=target, dependency_type=dep_type)
        self.edges[source].append(info)
        self.reverse_edges[target].append(info)

    def get_dependencies(self, spec_path: str, types: list[DependencyType] | None = None) -> list[DependencyInfo]:
        edges = self.edges.get(spec_path, [])
        if not types:
            return list(edges)
        return [e for e in edges if e.dependency_type in types]

    def validate_dependencies(self, specs: list[str]) -> list[DependencyConflict]:
        conflicts: list[DependencyConflict] = []
        spec_set = set(specs)
        for spec in specs:
            for dep in self.get_dependencies(spec, [DependencyType.INHERITS, DependencyType.REQUIRES]):
                if dep.target_spec not in spec_set and dep.target_spec not in self.nodes:
                    conflicts.append(
                        DependencyConflict(
                            conflict_type="missing",
                            description=f"缺失依赖: {spec} 需要 {dep.target_spec}",
                            affected_specs=[spec, dep.target_spec],
                            suggested_resolution="请补充依赖规范或移除依赖声明",
                        )
                    )
        return conflicts

    def detect_circular_dependencies(self) -> list[list[str]]:
        with self._lock:
            visited: set[str] = set()
            stack: set[str] = set()
            cycles: list[list[str]] = []

            def dfs(node: str, path: list[str]) -> None:
                visited.add(node)
                stack.add(node)
                path.append(node)

                for dep in self.get_dependencies(node, [DependencyType.INHERITS, DependencyType.REQUIRES]):
                    target = dep.target_spec
                    if target not in self.nodes:
                        continue
                    if target not in visited:
                        dfs(target, path.copy())
                    elif target in stack and target in path:
                        idx = path.index(target)
                        cycles.append(path[idx:] + [target])

                stack.discard(node)

            for node in list(self.nodes.keys()):
                if node not in visited:
                    dfs(node, [])

            return cycles

    def topological_sort(self, specs: list[str]) -> tuple[list[str], list[DependencyConflict]]:
        spec_set = set(specs)
        indegree: dict[str, int] = dict.fromkeys(specs, 0)
        graph: dict[str, set[str]] = {s: set() for s in specs}
        conflicts: list[DependencyConflict] = []

        for s in specs:
            for dep in self.get_dependencies(s, [DependencyType.INHERITS, DependencyType.REQUIRES]):
                if dep.target_spec in spec_set:
                    if dep.target_spec not in graph:
                        graph[dep.target_spec] = set()
                    graph[dep.target_spec].add(s)
                    indegree[s] += 1

        queue = deque([s for s in specs if indegree.get(s, 0) == 0])
        ordered: list[str] = []

        while queue:
            node = queue.popleft()
            ordered.append(node)
            for neighbor in graph.get(node, set()):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(specs):
            remaining = [s for s in specs if s not in ordered]
            conflicts.append(
                DependencyConflict(
                    conflict_type="circular",
                    description=f"拓扑排序失败,可能存在循环依赖: {', '.join(remaining)}",
                    affected_specs=remaining,
                    suggested_resolution="请移除循环依赖关系",
                )
            )
            ordered.extend(remaining)

        return ordered, conflicts

    def get_dependency_levels(self, specs: list[str]) -> dict[str, int]:
        levels: dict[str, int] = {}

        def calculate_level(spec: str, visited: set[str]) -> int:
            if spec in visited:
                return 0
            if spec in levels:
                return levels[spec]

            visited.add(spec)
            max_dep_level = -1
            dependencies = self.get_dependencies(spec, [DependencyType.INHERITS, DependencyType.REQUIRES])
            for dep in dependencies:
                if dep.target_spec in specs:
                    dep_level = calculate_level(dep.target_spec, visited.copy())
                    max_dep_level = max(max_dep_level, dep_level)
            level = max_dep_level + 1
            levels[spec] = level
            return level

        for spec in specs:
            if spec not in levels:
                calculate_level(spec, set())
        return levels
