"""Tests for dependency_manager (DependencyGraph and helpers)."""

from __future__ import annotations

import pytest

from apps.core.config.steering.dependency_manager import (
    DependencyGraph,
    DependencyInfo,
    DependencyType,
    LoadOrderStrategy,
    SpecificationMetadata,
    DependencyConflict,
    LoadOrderResult,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_dependency_info(self):
        di = DependencyInfo(
            source_spec="a",
            target_spec="b",
            dependency_type=DependencyType.REQUIRES,
        )
        assert di.source_spec == "a"
        assert di.dependency_type == DependencyType.REQUIRES

    def test_specification_metadata_defaults(self):
        sm = SpecificationMetadata(path="test.yaml", name="test")
        assert sm.version == "1.0.0"
        assert sm.priority == 0
        assert sm.inherits == []
        assert sm.requires == []

    def test_dependency_conflict(self):
        dc = DependencyConflict(
            conflict_type="circular",
            description="cycle detected",
            affected_specs=["a", "b"],
        )
        assert dc.conflict_type == "circular"

    def test_load_order_result(self):
        lor = LoadOrderResult(
            ordered_specs=["a", "b"],
            dependency_levels={"a": 0, "b": 1},
            warnings=[],
        )
        assert lor.ordered_specs == ["a", "b"]


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    def test_empty_graph(self):
        g = DependencyGraph()
        assert g.get_dependencies("a") == []
        assert g.get_dependents("a") == []

    def test_add_and_get(self):
        g = DependencyGraph()
        meta = SpecificationMetadata(
            path="a",
            name="A",
            requires=["b"],
        )
        g.add_specification(meta)
        deps = g.get_dependencies("a")
        assert len(deps) == 1
        assert deps[0].target_spec == "b"
        assert deps[0].dependency_type == DependencyType.REQUIRES

    def test_reverse_edges(self):
        g = DependencyGraph()
        meta = SpecificationMetadata(path="a", name="A", requires=["b"])
        g.add_specification(meta)
        dependents = g.get_dependents("b")
        assert len(dependents) == 1
        assert dependents[0].source_spec == "a"

    def test_inherits_dependency(self):
        g = DependencyGraph()
        meta = SpecificationMetadata(path="child", name="Child", inherits=["parent"])
        g.add_specification(meta)
        deps = g.get_dependencies("child", [DependencyType.INHERITS])
        assert len(deps) == 1
        assert deps[0].dependency_type == DependencyType.INHERITS

    def test_optional_dependency(self):
        g = DependencyGraph()
        meta = SpecificationMetadata(path="a", name="A", optional_deps=["opt"])
        g.add_specification(meta)
        deps = g.get_dependencies("a", [DependencyType.OPTIONAL])
        assert len(deps) == 1

    def test_conflicts_dependency(self):
        g = DependencyGraph()
        meta = SpecificationMetadata(path="a", name="A", conflicts=["enemy"])
        g.add_specification(meta)
        deps = g.get_dependencies("a", [DependencyType.CONFLICTS])
        assert len(deps) == 1

    def test_filter_by_type(self):
        g = DependencyGraph()
        meta = SpecificationMetadata(path="a", name="A", requires=["b"], inherits=["c"])
        g.add_specification(meta)
        deps = g.get_dependencies("a", [DependencyType.REQUIRES])
        assert len(deps) == 1
        assert deps[0].target_spec == "b"

    def test_detect_circular_no_cycle(self):
        g = DependencyGraph()
        meta_a = SpecificationMetadata(path="a", name="A", requires=["b"])
        meta_b = SpecificationMetadata(path="b", name="B")
        g.add_specification(meta_a)
        g.add_specification(meta_b)
        cycles = g.detect_circular_dependencies()
        assert cycles == []

    def test_detect_circular_with_cycle(self):
        g = DependencyGraph()
        meta_a = SpecificationMetadata(path="a", name="A", requires=["b"])
        meta_b = SpecificationMetadata(path="b", name="B", requires=["a"])
        g.add_specification(meta_a)
        g.add_specification(meta_b)
        cycles = g.detect_circular_dependencies()
        assert len(cycles) > 0


# ---------------------------------------------------------------------------
# DependencyType and LoadOrderStrategy enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_dependency_type_values(self):
        assert DependencyType.INHERITS.value == "inherits"
        assert DependencyType.REQUIRES.value == "requires"
        assert DependencyType.OPTIONAL.value == "optional"
        assert DependencyType.CONFLICTS.value == "conflicts"

    def test_load_order_strategy_values(self):
        assert LoadOrderStrategy.TOPOLOGICAL.value == "topological"
        assert LoadOrderStrategy.PRIORITY.value == "priority"
