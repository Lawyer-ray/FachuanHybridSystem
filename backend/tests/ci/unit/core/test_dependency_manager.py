"""Unit tests for core.config.steering.dependency_manager module."""

from __future__ import annotations

import pytest

from apps.core.config.steering.dependency_manager import (
    DependencyConflict,
    DependencyGraph,
    DependencyInfo,
    DependencyType,
    LoadOrderResult,
    LoadOrderStrategy,
    SpecificationMetadata,
    SteeringDependencyManager,
    create_dependency_manager_from_config,
)


class TestDependencyGraphBasic:
    """测试 DependencyGraph 基本操作"""

    def test_add_specification(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(path="a.md", name="A")
        graph.add_specification(meta)
        assert "a.md" in graph.nodes

    def test_get_dependencies_empty(self) -> None:
        graph = DependencyGraph()
        assert graph.get_dependencies("nonexistent.md") == []

    def test_add_with_requires(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(path="a.md", name="A", requires=["b.md"])
        graph.add_specification(meta)
        deps = graph.get_dependencies("a.md", [DependencyType.REQUIRES])
        assert len(deps) == 1
        assert deps[0].target_spec == "b.md"

    def test_add_with_inherits(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(path="a.md", name="A", inherits=["base.md"])
        graph.add_specification(meta)
        deps = graph.get_dependencies("a.md", [DependencyType.INHERITS])
        assert len(deps) == 1
        assert deps[0].target_spec == "base.md"

    def test_add_with_optional(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(path="a.md", name="A", optional_deps=["opt.md"])
        graph.add_specification(meta)
        deps = graph.get_dependencies("a.md", [DependencyType.OPTIONAL])
        assert len(deps) == 1

    def test_add_with_conflicts(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(path="a.md", name="A", conflicts=["bad.md"])
        graph.add_specification(meta)
        deps = graph.get_dependencies("a.md", [DependencyType.CONFLICTS])
        assert len(deps) == 1
        # conflicts should NOT create reverse edges
        assert graph.get_dependents("bad.md") == []

    def test_get_dependents(self) -> None:
        graph = DependencyGraph()
        meta = SpecificationMetadata(path="a.md", name="A", requires=["b.md"])
        graph.add_specification(meta)
        dependents = graph.get_dependents("b.md", [DependencyType.REQUIRES])
        assert len(dependents) == 1
        assert dependents[0].source_spec == "a.md"


class TestDependencyGraphCircular:
    """测试循环依赖检测"""

    def test_no_cycles(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        assert graph.detect_circular_dependencies() == []

    def test_detects_simple_cycle(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B", requires=["a.md"]))
        cycles = graph.detect_circular_dependencies()
        assert len(cycles) >= 1

    def test_self_referencing_cycle(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["a.md"]))
        cycles = graph.detect_circular_dependencies()
        assert len(cycles) >= 1


class TestDependencyGraphTopologicalSort:
    """测试拓扑排序"""

    def test_simple_sort(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        result, conflicts = graph.topological_sort(["a.md", "b.md"])
        assert result.index("b.md") < result.index("a.md")
        assert len(conflicts) == 0

    def test_sort_with_cycle(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B", requires=["a.md"]))
        result, conflicts = graph.topological_sort(["a.md", "b.md"])
        assert len(result) == 2
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "circular"

    def test_empty_specs(self) -> None:
        graph = DependencyGraph()
        result, conflicts = graph.topological_sort([])
        assert result == []
        assert conflicts == []

    def test_no_dependencies(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A"))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        result, conflicts = graph.topological_sort(["a.md", "b.md"])
        assert len(result) == 2
        assert len(conflicts) == 0


class TestDependencyGraphValidate:
    """测试依赖验证"""

    def test_missing_required_dep(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["missing.md"]))
        conflicts = graph.validate_dependencies(["a.md"])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "missing"

    def test_no_conflicts(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        conflicts = graph.validate_dependencies(["a.md", "b.md"])
        assert len(conflicts) == 0

    def test_conflict_detected(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", conflicts=["b.md"]))
        conflicts = graph.validate_dependencies(["a.md", "b.md"])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "conflict"


class TestDependencyGraphLevels:
    """测试依赖层级计算"""

    def test_root_has_level_zero(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A"))
        levels = graph.get_dependency_levels(["a.md"])
        assert levels["a.md"] == 0

    def test_child_has_higher_level(self) -> None:
        graph = DependencyGraph()
        graph.add_specification(SpecificationMetadata(path="a.md", name="A", requires=["b.md"]))
        graph.add_specification(SpecificationMetadata(path="b.md", name="B"))
        levels = graph.get_dependency_levels(["a.md", "b.md"])
        assert levels["b.md"] == 0
        assert levels["a.md"] == 1


class TestSteeringDependencyManager:
    """测试 SteeringDependencyManager"""

    def test_init_with_empty_root(self, tmp_path) -> None:
        config = {"auto_resolve": False, "circular_detection": True, "load_order_strategy": "dependency"}
        mgr = SteeringDependencyManager(config, steering_root=str(tmp_path / "nonexistent"))
        assert mgr.auto_resolve is False

    def test_normalize_dependency_list(self, tmp_path) -> None:
        config = {"auto_resolve": False}
        mgr = SteeringDependencyManager(config, steering_root=str(tmp_path / "nonexistent"))
        assert mgr._normalize_dependency_list("single") == ["single"]
        assert mgr._normalize_dependency_list(["a", "b"]) == ["a", "b"]
        assert mgr._normalize_dependency_list(42) == []

    def test_resolve_load_order_alphabetical(self, tmp_path) -> None:
        config = {"auto_resolve": False, "load_order_strategy": "alphabetical"}
        mgr = SteeringDependencyManager(config, steering_root=str(tmp_path / "nonexistent"))
        result = mgr.resolve_load_order(["b.md", "a.md", "c.md"])
        assert result.ordered_specs == ["a.md", "b.md", "c.md"]

    def test_get_dependency_info_nonexistent(self, tmp_path) -> None:
        config = {}
        mgr = SteeringDependencyManager(config, steering_root=str(tmp_path / "nonexistent"))
        info = mgr.get_dependency_info("nonexistent.md")
        assert "error" in info

    def test_get_statistics(self, tmp_path) -> None:
        config = {}
        mgr = SteeringDependencyManager(config, steering_root=str(tmp_path / "nonexistent"))
        stats = mgr.get_statistics()
        assert stats["total_specifications"] == 0
        assert stats["total_dependencies"] == 0


class TestCreateDependencyManagerFromConfig:
    def test_creates_manager(self, tmp_path) -> None:
        mgr = create_dependency_manager_from_config({}, str(tmp_path))
        assert isinstance(mgr, SteeringDependencyManager)


class TestDependencyConflict:
    def test_fields(self) -> None:
        c = DependencyConflict(
            conflict_type="circular",
            description="cycle detected",
            affected_specs=["a.md", "b.md"],
            suggested_resolution="remove cycle",
        )
        assert c.conflict_type == "circular"
        assert len(c.affected_specs) == 2


class TestLoadOrderResult:
    def test_fields(self) -> None:
        r = LoadOrderResult(
            ordered_specs=["a.md"],
            dependency_levels={"a.md": 0},
            warnings=[],
        )
        assert r.ordered_specs == ["a.md"]
        assert r.metadata == {}
